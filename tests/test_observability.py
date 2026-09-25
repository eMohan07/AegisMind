from __future__ import annotations

import json
import logging

import httpx
import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.ports import RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import Chunk

from aegismind_core.app import create_app
from aegismind_core.observability import (
    JsonLogFormatter,
    PrometheusTelemetryAdapter,
    current_span_id,
    current_trace_id,
    init_tracing,
    record_authz_evaluation,
    record_overfetch_ratio,
    record_reranker_duration,
    record_stage_duration,
    render_prometheus_metrics,
    set_correlation_id,
    trace_span,
)
from aegismind_core.routes import CoreState


@pytest.fixture
def test_setup() -> tuple[CoreState, RetrievalPipeline]:
    vector_store = MemoryVectorStoreAdapter()
    authz = MemoryAuthzAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()
    telemetry = PrometheusTelemetryAdapter()

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
        telemetry=telemetry,
    )

    state = CoreState(
        retrieval_pipeline=pipeline,
        authz=authz,
        vector_store=vector_store,
    )
    return state, pipeline


def test_structured_json_logging_format() -> None:
    formatter = JsonLogFormatter()
    set_correlation_id("test-corr-id-999")

    record = logging.LogRecord(
        name="aegismind.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=50,
        msg="Test event message for %s",
        args=("observability",),
        exc_info=None,
    )

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["logger"] == "aegismind.test"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test event message for observability"
    assert parsed["correlation_id"] == "test-corr-id-999"
    assert "timestamp" in parsed


def test_opentelemetry_trace_context() -> None:
    init_tracing("test-tracer")

    assert current_trace_id() is None
    assert current_span_id() is None

    with trace_span("test.parent.span", attributes={"env": "test"}):
        t_id = current_trace_id()
        s_id = current_span_id()
        assert t_id is not None and len(t_id) == 32
        assert s_id is not None and len(s_id) == 16

        formatter = JsonLogFormatter()
        record = logging.LogRecord(
            name="aegismind.tracer",
            level=logging.INFO,
            pathname=__file__,
            lineno=80,
            msg="Span active log",
            args=(),
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["trace_id"] == t_id
        assert parsed["span_id"] == s_id

    # Outside the span context
    assert current_trace_id() is None


def test_prometheus_metrics_recording_and_alert(caplog: pytest.LogCaptureFixture) -> None:
    tenant = "tenant-obs-test"

    record_authz_evaluation(tenant_id=tenant, evaluated=10, denied=4)
    record_reranker_duration(duration_seconds=0.042)
    record_stage_duration(stage="stage_5_authz", duration_seconds=0.015)

    with caplog.at_level(logging.WARNING):
        # Effectiveness 0.25 is below 0.3 threshold; triggers alert warning
        record_overfetch_ratio(tenant_id=tenant, ratio=0.25)

    assert any(
        "aegismind_overfetch_effectiveness dropped below 0.3" in r.message for r in caplog.records
    )

    raw_metrics = render_prometheus_metrics().decode("utf-8")
    assert "aegismind_authz_chunks_evaluated_total" in raw_metrics
    assert "aegismind_authz_chunks_denied_total" in raw_metrics
    assert "aegismind_authz_deny_rate" in raw_metrics
    assert "aegismind_overfetch_effectiveness" in raw_metrics
    assert "aegismind_reranker_latency_seconds" in raw_metrics
    assert "aegismind_query_latency_seconds" in raw_metrics


@pytest.mark.asyncio
async def test_api_correlation_id_and_metrics_endpoint(
    test_setup: tuple[CoreState, RetrievalPipeline],
) -> None:
    state, pipeline = test_setup
    app = create_app(state=state)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Request with explicit X-Correlation-ID
        res1 = await client.get("/healthz", headers={"X-Correlation-ID": "custom-uuid-4242"})
        assert res1.status_code == 200
        assert res1.headers.get("X-Correlation-ID") == "custom-uuid-4242"

        # Request without X-Correlation-ID generates one
        res2 = await client.get("/healthz")
        assert res2.status_code == 200
        generated_cid = res2.headers.get("X-Correlation-ID")
        assert generated_cid is not None
        assert len(generated_cid) > 0

        # Check /metrics endpoint
        res_metrics = await client.get("/metrics")
        assert res_metrics.status_code == 200
        assert "text/plain" in res_metrics.headers.get("Content-Type", "")
        metrics_body = res_metrics.text
        assert "aegismind_query_latency_seconds" in metrics_body

        # Check /api/v1/metrics endpoint
        res_api_metrics = await client.get("/api/v1/metrics")
        assert res_api_metrics.status_code == 200
        assert "aegismind_query_latency_seconds" in res_api_metrics.text


@pytest.mark.asyncio
async def test_end_to_end_search_telemetry_flow(
    test_setup: tuple[CoreState, RetrievalPipeline],
) -> None:
    state, pipeline = test_setup

    # Seed vector store and permissions
    chunk = Chunk(
        id="chk_telemetry_1",
        document_id="doc_telemetry_1",
        content="Enterprise metrics and telemetry verification chunk",
        dense_vector=[0.1] * 64,
        metadata={"title": "Telemetry Guide", "tenant_id": "tenant-corp"},
    )
    assert state.vector_store is not None
    assert state.authz is not None
    await state.vector_store.upsert([chunk])
    await state.authz.write_tuples(
        [
            RelationshipTuple(
                resource="document:doc_telemetry_1",
                relation="viewer",
                subject="user:alice",
            )
        ]
    )

    app = create_app(state=state)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        search_payload = {
            "query": "verification chunk",
            "principal_id": "alice",
            "tenant_id": "tenant-corp",
            "top_k": 5,
        }
        res = await client.post(
            "/api/v1/search",
            json=search_payload,
            headers={"X-Correlation-ID": "search-corr-888"},
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["results"]) >= 1

        # Check metrics updated after search execution
        metrics_res = await client.get("/metrics")
        body = metrics_res.text
        assert 'stage="stage_5_authz"' in body
        assert 'stage="stage_6_reranking"' in body
        assert 'tenant_id="tenant-corp"' in body
