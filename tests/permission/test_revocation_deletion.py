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
async def test_immediate_permission_revocation_and_deletion() -> None:
    """Verify that permission revocations and document deletions take effect immediately."""
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

    # 1. Ingest document chunk
    chunk = Chunk(
        id="chunk_critical_1",
        document_id="doc_critical",
        content="Mission critical zero-day mitigation protocol and key material.",
        embedding=[0.25] * 8,
        metadata={"title": "Zero-Day Mitigation"},
    )
    await vector_store.upsert([chunk])

    # 2. Grant viewer permission to alice
    grant_tuple = RelationshipTuple(
        resource="document:doc_critical",
        relation="viewer",
        subject="user:alice",
    )
    await authz.write_tuples([grant_tuple])

    alice = Principal(id="alice", type="user")

    # 3. Verify Alice initially has access
    initial_res = await pipeline.execute(
        query="zero-day mitigation key material",
        principal=alice,
        top_k=5,
    )
    assert len(initial_res.results) == 1
    assert initial_res.results[0].document_id == "doc_critical"

    # 4. Immediate Revocation of Alice's permission
    await authz.delete_tuples([grant_tuple])

    # 5. Verify Alice's access is immediately revoked with zero delay
    revoked_res = await pipeline.execute(
        query="zero-day mitigation key material",
        principal=alice,
        top_k=5,
    )
    assert len(revoked_res.results) == 0
    assert revoked_res.authorized_candidates_count == 0

    # 6. Re-grant and then test complete document deletion from vector storage
    await authz.write_tuples([grant_tuple])
    regranted_res = await pipeline.execute(
        query="zero-day mitigation key material",
        principal=alice,
        top_k=5,
    )
    assert len(regranted_res.results) == 1

    # Delete chunk from vector store and revoke tuples
    await vector_store.delete([chunk.id])
    await authz.delete_tuples([grant_tuple])

    # 7. Verify deleted document is never returned
    deleted_res = await pipeline.execute(
        query="zero-day mitigation key material",
        principal=alice,
        top_k=5,
    )
    assert len(deleted_res.results) == 0
    assert deleted_res.total_candidates_evaluated == 0
