from __future__ import annotations

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.ports import RelationshipTuple
from aegismind_connector_google_drive.connector import GoogleDriveConnector
from aegismind_ingestion.adapters_parser import DoclingParserAdapter
from aegismind_ingestion.pipeline import IngestionPipeline
from aegismind_retrieval.adapters_model import (
    MockEmbedderAdapter,
    MockQueryRewriterAdapter,
    MockRerankerAdapter,
)
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.mmr import maximal_marginal_relevance
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_retrieval.ports import ScoredChunk
from aegismind_types import ACL, ChatTurn, Chunk, Principal
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegismind_core.routes import CoreState, create_routes


@pytest.mark.asyncio
async def test_stage_0_query_rewriting() -> None:
    """Verify Stage 0 query rewriting resolves pronouns against conversational chat history."""
    authz = MemoryAuthzAdapter()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()
    rewriter = MockQueryRewriterAdapter()

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
        query_rewriter=rewriter,
    )

    history = [
        ChatTurn(
            role="user", content="Tell me about the global data retention policy in GDPR compliance"
        ),
        ChatTurn(
            role="assistant",
            content="The global data retention policy adheres strictly to European guidelines.",
        ),
    ]

    alice = Principal(id="alice", type="user", tenant_id="corp-default")
    result = await pipeline.execute(
        query="what about the EU one",
        principal=alice,
        chat_history=history,
    )

    assert result.rewritten_query is not None
    assert "data retention policy" in result.rewritten_query or "GDPR" in result.rewritten_query


@pytest.mark.asyncio
async def test_stage_1_and_2_dense_sparse_rrf_and_query_type_overfetch() -> None:
    """Verify dual dense and sparse search, RRF fusion, and query type overfetch bounding."""
    authz = MemoryAuthzAdapter()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()

    # Create distinct chunks: one matching dense semantics, one matching lexical keywords
    chunk1 = Chunk(
        id="c1",
        document_id="doc_alpha",
        index=1,
        content="Alpha architecture document with detailed network topologies",
        embedding=await embedder.embed_query(
            "Alpha architecture document with detailed network topologies"
        ),
        sparse_embedding=await embedder.embed_sparse_query(
            "Alpha architecture document with detailed network topologies"
        ),
        metadata={"tenant_id": "corp-default", "title": "Doc Alpha"},
        acl=ACL(is_public=False),
    )
    chunk2 = Chunk(
        id="c2",
        document_id="doc_beta",
        index=1,
        content="Beta confidential compensation reports and employee salaries",
        embedding=await embedder.embed_query(
            "Beta confidential compensation reports and employee salaries"
        ),
        sparse_embedding=await embedder.embed_sparse_query(
            "Beta confidential compensation reports and employee salaries"
        ),
        metadata={"tenant_id": "corp-default", "title": "Doc Beta"},
        acl=ACL(is_public=False),
    )

    await vector_store.upsert([chunk1, chunk2])
    await authz.write_tuples(
        [
            RelationshipTuple(
                resource="document:doc_alpha", relation="viewer", subject="user:alice"
            ),
        ]
    )

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    alice = Principal(id="alice", type="user", tenant_id="corp-default")

    # Test with query_type='exploratory' (multiplier 4.5)
    res_exploratory = await pipeline.execute(
        query="network topologies and architecture",
        principal=alice,
        query_type="exploratory",
        top_k=1,
    )
    assert res_exploratory.overfetch_factor == 4.5
    assert len(res_exploratory.results) == 1
    assert res_exploratory.results[0].document_id == "doc_alpha"

    # Test deny rate calculation
    assert res_exploratory.deny_rate >= 0.0


def test_stage_7_mmr_diversity() -> None:
    """Verify MMR prevents top_k results from being dominated by near-duplicates."""
    doc_a_chunk1 = Chunk(
        id="a1",
        document_id="doc_A",
        content="Incident report 404: database connection pool exhausted on cluster primary",
        metadata={"title": "Doc A"},
    )
    doc_a_chunk2 = Chunk(
        id="a2",
        document_id="doc_A",
        content="Incident report 404: database connection pool exhausted on replica nodes",
        metadata={"title": "Doc A"},
    )
    doc_b_chunk1 = Chunk(
        id="b1",
        document_id="doc_B",
        content="Runbook 12: scaling redis cache clusters to mitigate database pressure",
        metadata={"title": "Doc B"},
    )

    candidates = [
        ScoredChunk(chunk=doc_a_chunk1, score=0.95),
        ScoredChunk(chunk=doc_a_chunk2, score=0.94),
        ScoredChunk(chunk=doc_b_chunk1, score=0.88),
    ]

    # Without MMR diversity, top 2 would be both from Doc A
    standard_top2 = candidates[:2]
    assert standard_top2[0].chunk.document_id == "doc_A"
    assert standard_top2[1].chunk.document_id == "doc_A"

    # With MMR diversity, Doc B should be promoted to ensure diverse source coverage
    mmr_results = maximal_marginal_relevance(candidates, top_n=2, lambda_mult=0.5)
    result_docs = [sc.chunk.document_id for sc in mmr_results]
    assert "doc_A" in result_docs
    assert "doc_B" in result_docs


@pytest.mark.asyncio
async def test_feedback_capture_api() -> None:
    """Verify user feedback endpoint records thumbs up/down and metadata for answer evaluation."""
    state = CoreState()
    router = create_routes(state)
    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)

    # 1. Post feedback
    payload = {
        "query": "How to rotate encryption keys?",
        "rewritten_query": "How to rotate AES-256 envelope encryption keys?",
        "retrieved_chunk_ids": ["chunk_sec_01", "chunk_sec_02"],
        "rating": "thumbs_up",
        "comment": "Accurate and provided deep citations.",
        "tenant_id": "corp-default",
    }
    resp = client.post("/api/v1/feedback", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["rating"] == "thumbs_up"
    assert data["query"] == payload["query"]
    assert len(data["retrieved_chunk_ids"]) == 2

    # 2. Get feedback list
    list_resp = client.get("/api/v1/feedback")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert list_data["entries"][0]["query"] == payload["query"]


@pytest.mark.asyncio
async def test_google_drive_pipeline_end_to_end() -> None:
    """Verify Google Drive connector ingestion and end-to-end Sacred Retrieval Pipeline."""
    authz = MemoryAuthzAdapter()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()
    rewriter = MockQueryRewriterAdapter()

    # 1. Ingest Google Drive sample records
    connector = GoogleDriveConnector()
    records = [r async for r in connector.read()]
    assert len(records) > 0

    ingestion = IngestionPipeline(
        parser=DoclingParserAdapter(),
        vector_store=vector_store,
        embedder=embedder,
        authz=authz,
    )

    summary = await ingestion.ingest_records(records)
    assert summary.chunks_indexed > 0
    assert summary.tuples_written > 0

    # Verify chunks have both dense and sparse representations
    for chunk in vector_store._chunks.values():
        assert chunk.embedding is not None
        assert chunk.sparse_embedding is not None

    # 2. Execute retrieval query
    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
        query_rewriter=rewriter,
    )

    # Extract allowed user from one of the records
    target_record = records[0]
    allowed_user = "user:employee@example.com"
    for p in target_record.acl.allowed_principals:
        if p.startswith("user:"):
            allowed_user = p[len("user:") :]
            break

    user_principal = Principal(id=allowed_user, type="user")
    query_text = str(target_record.payload.get("name") or "drive document")

    search_result = await pipeline.execute(
        query=query_text,
        principal=user_principal,
        top_k=3,
        query_type="factual",
    )

    assert search_result.query == query_text
    assert search_result.overfetch_factor == 3.0
    assert len(search_result.results) > 0
    assert search_result.results[0].citation is not None
