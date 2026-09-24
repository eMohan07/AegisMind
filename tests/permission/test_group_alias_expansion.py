from __future__ import annotations

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.mappers import acl_to_relationship_tuples
from aegismind_authz.ports import RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import ACL, Chunk, Principal


@pytest.mark.permission
@pytest.mark.asyncio
async def test_nested_group_membership_and_alias_expansion() -> None:
    """Verify group alias expansion and nested group authorization inheritance."""
    authz = MemoryAuthzAdapter()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=8)
    reranker = MockRerankerAdapter()

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    # 1. Test ACL to Zanzibar tuple mapping with group alias expansion
    source_acl = ACL(
        allowed_principals=["group:okta_cloud_admins"],
        is_public=False,
    )
    group_aliases = {
        "okta_cloud_admins": ["platform_leads", "security_architects"],
    }

    tuples = acl_to_relationship_tuples(
        resource_id="doc_cloud_spec",
        acl=source_acl,
        group_aliases=group_aliases,
    )

    # Verify both aliases were expanded
    subjects = {t.subject for t in tuples}
    assert "group:platform_leads#member" in subjects
    assert "group:security_architects#member" in subjects

    # 2. Add tuples to Authz including nested group hierarchy
    await authz.write_tuples(tuples)

    # Add nested group membership:
    # User Alice belongs to group:platform_leads
    alice_membership = RelationshipTuple(
        resource="group:platform_leads",
        relation="member",
        subject="user:alice",
    )
    # User Bob belongs to group:security_architects
    bob_membership = RelationshipTuple(
        resource="group:security_architects",
        relation="member",
        subject="user:bob",
    )
    await authz.write_tuples([alice_membership, bob_membership])

    # Ingest document chunk
    chunk = Chunk(
        id="chunk_cloud_1",
        document_id="doc_cloud_spec",
        content="Multi-region cloud infrastructure terraform specifications.",
        embedding=[0.2] * 8,
        metadata={"title": "Cloud Spec"},
    )
    await vector_store.upsert([chunk])

    alice = Principal(id="alice", type="user")
    bob = Principal(id="bob", type="user")
    charlie = Principal(id="charlie", type="user")  # External user

    # 3. Verify Alice and Bob gain access via their aliased group memberships
    alice_res = await pipeline.execute(
        query="terraform specifications cloud",
        principal=alice,
        top_k=5,
    )
    assert len(alice_res.results) == 1
    assert alice_res.results[0].document_id == "doc_cloud_spec"

    bob_res = await pipeline.execute(
        query="terraform specifications cloud",
        principal=bob,
        top_k=5,
    )
    assert len(bob_res.results) == 1
    assert bob_res.results[0].document_id == "doc_cloud_spec"

    # 4. Verify Charlie is denied access
    charlie_res = await pipeline.execute(
        query="terraform specifications cloud",
        principal=charlie,
        top_k=5,
    )
    assert len(charlie_res.results) == 0

    # 5. Revoke Alice from platform_leads and verify immediate revocation
    await authz.delete_tuples([alice_membership])
    revoked_alice_res = await pipeline.execute(
        query="terraform specifications cloud",
        principal=alice,
        top_k=5,
    )
    assert len(revoked_alice_res.results) == 0
