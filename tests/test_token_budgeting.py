from __future__ import annotations

from unittest.mock import AsyncMock

from aegismind_authz.ports import AuthzPort
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import PipelineResult, RetrievalPipeline
from aegismind_types import Citation, SearchResult
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegismind_core.adapters.llm import MockLLMAdapter
from aegismind_core.budgeting import apply_context_budget
from aegismind_core.routes import CoreState, create_routes


def _create_sample_search_results(count: int) -> list[SearchResult]:
    """Generate mock search results sorted by descending rerank score."""
    results = []
    for i in range(count):
        # 100 characters text ~ 25 tokens
        text = (
            f"Enterprise policy paragraph {i:02d}: "
            "Comprehensive access guidelines and zero-leakage protocols."
        )
        results.append(
            SearchResult(
                chunk_id=f"chunk_{i:02d}",
                document_id=f"doc_{i:02d}",
                title=f"Security Policy Document {i:02d}",
                uri=f"https://corp.internal/sec/{i:02d}",
                text=text,
                score=round(1.0 - (i * 0.04), 3),
                tenant_id="corp-default",
                citation=Citation(
                    chunk_id=f"chunk_{i:02d}",
                    document_id=f"doc_{i:02d}",
                    title=f"Security Policy Document {i:02d}",
                    uri=f"https://corp.internal/sec/{i:02d}",
                    snippet=text[:40],
                    score=round(1.0 - (i * 0.04), 3),
                    tenant_id="corp-default",
                ),
            )
        )
    return results


def test_context_budgeting_drops_lowest_scores_and_emits_notice() -> None:
    """Verify that 20 retrieved chunks are trimmed to 12, preserving top 12 chunks atomically."""
    results = _create_sample_search_results(20)
    mock_llm = MockLLMAdapter()

    # Measure tokens for prompt with exactly 12 chunks
    budget_for_12 = apply_context_budget(
        query="What is the access policy?",
        results=results[:12],
        llm=mock_llm,
        reserve_output_tokens=0,
    )
    exact_limit_for_12 = budget_for_12.total_tokens

    # Now run budgeting with all 20 chunks and limit set to exact_limit_for_12
    budget_result = apply_context_budget(
        query="What is the access policy?",
        results=results,
        llm=mock_llm,
        reserve_output_tokens=0,
        max_context_override=exact_limit_for_12,
    )

    # 1. Verify 8 chunks dropped, top 12 preserved
    assert budget_result.original_count == 20
    assert budget_result.final_count == 12
    assert budget_result.dropped_count == 8

    # 2. Verify surviving chunks are the top 12 highest-scoring chunks
    surviving_ids = [c.chunk_id for c in budget_result.chunks]
    expected_ids = [f"chunk_{i:02d}" for i in range(12)]
    assert surviving_ids == expected_ids

    # 3. Verify lowest scoring chunks (12 to 19) were removed
    for dropped_idx in range(12, 20):
        assert f"chunk_{dropped_idx:02d}" not in surviving_ids

    # 4. Verify notice is present with exact format
    expected_notice = "Note: Results trimmed from 20 to 12 due to context constraints."
    assert budget_result.notice == expected_notice

    # 5. Verify atomic units: no chunk was truncated mid-sentence
    for c in budget_result.chunks:
        assert c.text in budget_result.prompt


def test_context_budgeting_all_fit() -> None:
    """Verify that when all chunks fit, none are dropped and no notice is emitted."""
    results = _create_sample_search_results(5)
    mock_llm = MockLLMAdapter(context_window=10000)

    budget_result = apply_context_budget(
        query="What is the access policy?",
        results=results,
        llm=mock_llm,
        reserve_output_tokens=256,
        max_context_override=8192,
    )

    assert budget_result.original_count == 5
    assert budget_result.final_count == 5
    assert budget_result.dropped_count == 0
    assert budget_result.notice is None
    assert len(budget_result.chunks) == 5


def test_chat_sse_token_budgeting_integration() -> None:
    """Verify that /api/v1/chat streaming dynamically reduces top_k and appends notice."""
    results = _create_sample_search_results(20)
    mock_llm = MockLLMAdapter(
        default_response="Enterprise answer based on access-controlled documents."
    )

    # Calculate token size for exactly 12 chunks with 1024 reserved tokens
    budget_for_12 = apply_context_budget(
        query="policy summary",
        results=results[:12],
        llm=mock_llm,
        reserve_output_tokens=1024,
    )
    context_limit = budget_for_12.total_tokens + 1024
    mock_llm.context_window = context_limit

    # Setup retrieval mock returning 20 results
    mock_pipeline = AsyncMock(spec=RetrievalPipeline)
    mock_pipeline.execute.return_value = PipelineResult(
        query="policy summary",
        query_type="factual",
        results=results,
        total_candidates_evaluated=50,
        authorized_candidates_count=20,
        overfetch_factor=3.5,
    )

    state = CoreState(
        retrieval_pipeline=mock_pipeline,
        vector_store=MemoryVectorStoreAdapter(),
        authz=AsyncMock(spec=AuthzPort),
        llm=mock_llm,
    )
    router = create_routes(state)
    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)
    resp = client.get(
        "/api/v1/chat/stream",
        params={"query": "policy summary", "principal_id": "alice"},
    )
    assert resp.status_code == 200

    # Verify notice is appended to the stream tokens
    expected_notice = "Note: Results trimmed from 20 to 12 due to context constraints."
    assert expected_notice in resp.text

    # Verify done event contains reduced top_k: 12
    assert '"top_k": 12' in resp.text
    assert f'"notice": "{expected_notice}"' in resp.text
