from __future__ import annotations

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.ports import RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import PipelineResult, RetrievalPipeline
from aegismind_types import ACL, Chunk, Principal, TokenConsistency


@pytest.fixture
def authz_adapter() -> MemoryAuthzAdapter:
    adapter = MemoryAuthzAdapter()
    return adapter


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    chunks = []
    # Create 10 chunks across 5 documents in tenant_acme
    for i in range(1, 11):
        doc_num = (i + 1) // 2
        chunks.append(
            Chunk(
                id=f"chunk_{i}",
                document_id=f"doc_{doc_num}",
                index=i,
                content=f"Secret project information regarding quantum security topic {i}",
                embedding=[0.1 * (i % 5)] * 64,
                metadata={
                    "title": f"Document {doc_num} Overview",
                    "uri": f"https://wiki.corp.internal/doc/{doc_num}",
                    "tenant_id": "tenant_acme",
                },
                acl=ACL(is_public=False),
            )
        )
    return chunks


@pytest.mark.asyncio
async def test_sacred_enforcement_pipeline_lifecycle(
    authz_adapter: MemoryAuthzAdapter,
    sample_chunks: list[Chunk],
) -> None:
    # 1. Setup Vector Store, Embedder, Reranker
    vector_store = MemoryVectorStoreAdapter()
    await vector_store.upsert(sample_chunks)

    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()

    # 2. Grant access to only doc_1 and doc_2 for user alice
    await authz_adapter.write_tuples(
        [
            RelationshipTuple(resource="document:doc_1", relation="viewer", subject="user:alice"),
            RelationshipTuple(resource="document:doc_2", relation="viewer", subject="user:alice"),
        ]
    )

    pipeline = RetrievalPipeline(
        authz=authz_adapter,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    alice = Principal(
        id="alice",
        type="user",
        tenant_id="tenant_acme",
        attributes={"groups": ["engineering"]},
    )

    # 3. Execute search with top_k=2, overfetch_factor=4.0
    result: PipelineResult = await pipeline.execute(
        query="quantum security",
        principal=alice,
        top_k=2,
        overfetch_factor=4.0,
        consistency=TokenConsistency(requirement="at_least_as_fresh"),
    )

    # Assertions on pipeline contract
    assert result.query == "quantum security"
    assert result.overfetch_factor == 4.0

    # Overfetch factor 4.0 * top_k 2 = 8 candidates evaluated
    assert result.total_candidates_evaluated == 8

    # Only chunks from doc_1 and doc_2 should be authorized
    assert result.authorized_candidates_count > 0
    for res in result.results:
        assert res.document_id in {"doc_1", "doc_2"}

        # Verify deep-linked citations are attached
        assert res.citation is not None
        assert res.citation.chunk_id == res.chunk_id
        assert res.citation.document_id == res.document_id
        assert "wiki.corp.internal" in (res.citation.uri or "")
        assert res.citation.snippet.startswith("Secret project")
        assert res.citation.score > 0.0

    assert len(result.results) <= 2


@pytest.mark.asyncio
async def test_overfetch_factor_bounding(
    authz_adapter: MemoryAuthzAdapter,
    sample_chunks: list[Chunk],
) -> None:
    vector_store = MemoryVectorStoreAdapter()
    await vector_store.upsert(sample_chunks)

    pipeline = RetrievalPipeline(
        authz=authz_adapter,
        vector_store=vector_store,
        embedder=MockEmbedderAdapter(dimension=64),
        reranker=MockRerankerAdapter(),
    )

    user = Principal(id="bob", type="user", tenant_id="tenant_acme")

    # If requested factor is 1.0, it should be clamped to 3.0
    res_low = await pipeline.execute(
        query="security",
        principal=user,
        top_k=2,
        overfetch_factor=1.0,
    )
    assert res_low.overfetch_factor == 3.0

    # If requested factor is 10.0, it should be clamped to 5.0
    res_high = await pipeline.execute(
        query="security",
        principal=user,
        top_k=2,
        overfetch_factor=10.0,
    )
    assert res_high.overfetch_factor == 5.0


@pytest.mark.asyncio
async def test_complete_authorization_rejection(
    authz_adapter: MemoryAuthzAdapter,
    sample_chunks: list[Chunk],
) -> None:
    vector_store = MemoryVectorStoreAdapter()
    await vector_store.upsert(sample_chunks)

    pipeline = RetrievalPipeline(
        authz=authz_adapter,
        vector_store=vector_store,
        embedder=MockEmbedderAdapter(dimension=64),
        reranker=MockRerankerAdapter(),
    )

    # User with NO permissions on any document
    eve = Principal(id="eve", type="user", tenant_id="tenant_acme")

    res = await pipeline.execute(
        query="quantum security",
        principal=eve,
        top_k=5,
    )

    assert res.total_candidates_evaluated > 0
    assert res.authorized_candidates_count == 0
    assert len(res.results) == 0
