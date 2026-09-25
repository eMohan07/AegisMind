from __future__ import annotations

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.ports import RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import ACL, Chunk, Principal, TokenConsistency


@pytest.mark.permission
@pytest.mark.asyncio
async def test_instant_revocation_zero_stale_window() -> None:
    """Assert revoking user access via tuple delete immediately yields zero results."""
    authz = MemoryAuthzAdapter()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()

    # 1. Ingest confidential document
    doc_id = "doc_secret_merger_q4"
    chunk = Chunk(
        id="chunk_merger_01",
        document_id=doc_id,
        index=1,
        content="Confidential acquisition of Acme Technologies planned for Q4 closing",
        embedding=await embedder.embed_query("Confidential acquisition of Acme Technologies"),
        metadata={"title": "Q4 Merger Plan", "tenant_id": "corp-default"},
        acl=ACL(is_public=False),
    )
    await vector_store.upsert([chunk])

    # 2. Grant viewer access to user bob
    viewer_tuple = RelationshipTuple(
        resource=f"document:{doc_id}",
        relation="viewer",
        subject="user:bob",
    )
    await authz.write_tuples([viewer_tuple])

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    bob = Principal(id="bob", type="user", tenant_id="corp-default")

    # 3. Verify bob can access the document
    res_before = await pipeline.execute(
        query="acquisition of Acme Technologies",
        principal=bob,
        consistency=TokenConsistency(requirement="at_least_as_fresh"),
    )
    assert len(res_before.results) == 1
    assert res_before.results[0].document_id == doc_id

    # 4. Revoke bob's access immediately (e.g. employee role termination)
    await authz.delete_tuples([viewer_tuple])

    # 5. Immediate subsequent query within milliseconds must return zero results
    res_after = await pipeline.execute(
        query="acquisition of Acme Technologies",
        principal=bob,
        consistency=TokenConsistency(requirement="at_least_as_fresh"),
    )
    assert len(res_after.results) == 0
    assert res_after.authorized_candidates_count == 0
    assert res_after.deny_rate == 1.0
