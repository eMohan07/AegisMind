from __future__ import annotations

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.ports import RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import Chunk, Principal


@pytest.mark.permission
@pytest.mark.asyncio
async def test_multi_tenant_multi_user_redteam_isolation() -> None:
    """Red-team simulation verifying that unauthorized users can NEVER retrieve restricted docs."""
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

    # 1. Ingest Documents into Vector Store
    # Doc 1: Highly confidential document in Tenant Alpha
    c1 = Chunk(
        id="chunk_alpha_secret_1",
        document_id="doc_alpha_secret",
        content="Acme Corp acquisition term sheet and merger valuation of 500M USD.",
        embedding=[0.5] * 8,
        metadata={"title": "M&A Term Sheet", "tenant_id": "tenant_alpha"},
    )
    # Doc 2: Engineering document in Tenant Alpha
    c2 = Chunk(
        id="chunk_alpha_eng_1",
        document_id="doc_alpha_eng",
        content=(
            "Engineering infrastructure guidelines, Kubernetes cluster sharding, and VPC peering."
        ),
        embedding=[0.1] * 8,
        metadata={"title": "Infrastructure Guide", "tenant_id": "tenant_alpha"},
    )
    # Doc 3: Public document in Tenant Alpha
    c3 = Chunk(
        id="chunk_alpha_pub_1",
        document_id="doc_alpha_pub",
        content="AegisMind general employee handbook and annual company holiday schedule.",
        embedding=[0.05] * 8,
        metadata={"title": "Company Handbook", "tenant_id": "tenant_alpha"},
    )
    # Doc 4: Document in Tenant Beta with matching keywords
    c4 = Chunk(
        id="chunk_beta_secret_1",
        document_id="doc_beta_secret",
        content="Tenant Beta analysis of Acme Corp acquisition term sheet and market valuation.",
        embedding=[0.5] * 8,
        metadata={"title": "Beta Competitor Analysis", "tenant_id": "tenant_beta"},
    )

    await vector_store.upsert([c1, c2, c3, c4])

    # 2. Write Zanzibar Relationship Tuples
    tuples = [
        # doc_alpha_secret: accessible to alice and executives
        RelationshipTuple(
            resource="document:doc_alpha_secret",
            relation="viewer",
            subject="user:alice",
        ),
        RelationshipTuple(
            resource="document:doc_alpha_secret",
            relation="viewer",
            subject="group:executives#member",
        ),
        # doc_alpha_eng: accessible to engineering group
        RelationshipTuple(
            resource="document:doc_alpha_eng",
            relation="viewer",
            subject="group:engineering#member",
        ),
        RelationshipTuple(
            resource="group:engineering",
            relation="member",
            subject="user:bob",
        ),
        # doc_alpha_pub: accessible to all users via wildcard
        RelationshipTuple(
            resource="document:doc_alpha_pub",
            relation="viewer",
            subject="user:*",
        ),
        # doc_beta_secret: accessible only to charlie in tenant_beta
        RelationshipTuple(
            resource="document:doc_beta_secret",
            relation="viewer",
            subject="user:charlie",
        ),
    ]
    await authz.write_tuples(tuples)

    # 3. Test Attack Vector 1: Cross-Tenant Data Leakage
    # Mallory (tenant_beta) executes exact match query for Tenant Alpha's confidential term sheet
    mallory_beta = Principal(id="mallory", type="user", tenant_id="tenant_beta")
    result_mallory = await pipeline.execute(
        query="Acme Corp acquisition term sheet",
        principal=mallory_beta,
        top_k=10,
    )
    # Mallory MUST NOT receive doc_alpha_secret or any tenant_alpha doc
    returned_docs_mallory = {r.document_id for r in result_mallory.results}
    assert "doc_alpha_secret" not in returned_docs_mallory
    assert "doc_alpha_eng" not in returned_docs_mallory
    assert "doc_alpha_pub" not in returned_docs_mallory

    # 4. Test Attack Vector 2: Intra-Tenant Privilege Escalation
    # Bob is an engineer in tenant_alpha, but NOT an executive.
    # Bob queries for the exact phrase in doc_alpha_secret.
    bob_alpha = Principal(
        id="bob",
        type="user",
        tenant_id="tenant_alpha",
        attributes={"groups": ["engineering"]},
    )
    result_bob = await pipeline.execute(
        query="Acme Corp acquisition term sheet and merger valuation",
        principal=bob_alpha,
        top_k=10,
    )
    returned_docs_bob = {r.document_id for r in result_bob.results}
    # Bob MUST NOT receive doc_alpha_secret or doc_beta_secret
    assert "doc_alpha_secret" not in returned_docs_bob
    assert "doc_beta_secret" not in returned_docs_bob
    # Bob MUST have evaluated candidates, but authz filtered them out
    assert result_bob.total_candidates_evaluated > 0

    # 5. Test Authorized Access: Alice (Executive in Tenant Alpha)
    alice_alpha = Principal(
        id="alice",
        type="user",
        tenant_id="tenant_alpha",
        attributes={"groups": ["executives"]},
    )
    result_alice = await pipeline.execute(
        query="Acme Corp acquisition term sheet and merger valuation",
        principal=alice_alpha,
        top_k=10,
    )
    returned_docs_alice = {r.document_id for r in result_alice.results}
    assert "doc_alpha_secret" in returned_docs_alice
    assert "doc_beta_secret" not in returned_docs_alice  # Tenant boundary preserved

    # 6. Test Public Document Access within Tenant
    result_bob_handbook = await pipeline.execute(
        query="employee handbook holiday schedule",
        principal=bob_alpha,
        top_k=5,
    )
    returned_docs_handbook = {r.document_id for r in result_bob_handbook.results}
    assert "doc_alpha_pub" in returned_docs_handbook
