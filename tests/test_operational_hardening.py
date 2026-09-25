from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_connector_sdk.retry import async_retry
from aegismind_ingestion.dlq import MemoryDLQAdapter
from aegismind_ingestion.pipeline import IngestionPipeline
from aegismind_ingestion.ports import ParserPort
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import Document, Record
from httpx import ASGITransport, AsyncClient

from aegismind_core.app import create_app
from aegismind_core.routes import CoreState


# 1. Tests for async_retry decorator
class TransientError(Exception):
    pass


class FatalError(Exception):
    pass


@pytest.mark.asyncio
async def test_async_retry_succeeds_after_transient_failures() -> None:
    calls = 0

    @async_retry(max_retries=3, base_delay=0.01, max_delay=0.05, retry_exceptions=(TransientError,))
    async def flaky_fetch() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientError("Connection timeout")
        return "success"

    result = await flaky_fetch()
    assert result == "success"
    assert calls == 3


@pytest.mark.asyncio
async def test_async_retry_raises_when_retries_exhausted() -> None:
    calls = 0

    @async_retry(max_retries=2, base_delay=0.01, max_delay=0.05, retry_exceptions=(TransientError,))
    async def always_failing() -> None:
        nonlocal calls
        calls += 1
        raise TransientError("Persistent service failure")

    with pytest.raises(TransientError, match="Persistent service failure"):
        await always_failing()

    assert calls == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_async_retry_does_not_retry_unhandled_exceptions() -> None:
    calls = 0

    @async_retry(max_retries=3, base_delay=0.01, max_delay=0.05, retry_exceptions=(TransientError,))
    async def fatal_operation() -> None:
        nonlocal calls
        calls += 1
        raise FatalError("Unrecoverable error")

    with pytest.raises(FatalError):
        await fatal_operation()

    assert calls == 1


# 2. Tests for MemoryDLQAdapter
@pytest.mark.asyncio
async def test_memory_dlq_adapter_lifecycle() -> None:
    dlq = MemoryDLQAdapter()

    # Enqueue items
    item1 = await dlq.enqueue(
        connector_id="github",
        resource_id="pr_101",
        error_message="Rate limit 429",
        payload={"repo": "aegismind/core"},
    )
    assert item1.status == "pending"
    assert item1.retry_count == 0

    item2 = await dlq.enqueue(
        connector_id="slack",
        resource_id="msg_202",
        error_message="Payload corrupted",
        payload={"channel": "general"},
    )
    assert item2.resource_id == "msg_202"

    # List items
    all_items = await dlq.list_items()
    assert len(all_items) == 2

    github_items = await dlq.list_items(connector_id="github")
    assert len(github_items) == 1
    assert github_items[0].resource_id == "pr_101"

    # Get single item
    fetched = await dlq.get_item(item1.id)
    assert fetched is not None
    assert fetched.id == item1.id

    # Update status
    updated = await dlq.update_status(item1.id, status="retried")
    assert updated is not None
    assert updated.status == "retried"
    assert updated.retry_count == 1

    # Delete item
    deleted = await dlq.delete_item(item1.id)
    assert deleted is True
    assert await dlq.get_item(item1.id) is None


# 3. Tests for IngestionPipeline DLQ routing
class MockFailingParser(ParserPort):
    async def parse(self, record: Record) -> Document:
        raise ValueError(f"Parsing failed for {record.id}")


@pytest.mark.asyncio
async def test_ingestion_pipeline_enqueues_to_dlq_on_failure() -> None:
    dlq = MemoryDLQAdapter()
    pipeline = IngestionPipeline(
        parser=MockFailingParser(),
        vector_store=MemoryVectorStoreAdapter(),
        embedder=MockEmbedderAdapter(dimension=16),
        authz=MemoryAuthzAdapter(),
        dlq=dlq,
    )

    record = Record(
        id="rec_err_1",
        source="confluence",
        external_id="conf_999",
        payload={"raw": "test document"},
    )

    summary = await pipeline.ingest_records([record])
    assert len(summary.errors) == 1
    assert summary.documents_created == 0

    # Verify DLQ received the failed record
    dlq_items = await dlq.list_items()
    assert len(dlq_items) == 1
    assert dlq_items[0].connector_id == "confluence"
    assert dlq_items[0].resource_id == "rec_err_1"
    assert "Parsing failed" in dlq_items[0].error_message


# 4. Tests for Probes and DLQ Endpoints via FastAPI
@pytest.fixture
def test_state() -> CoreState:
    vector_store = MemoryVectorStoreAdapter()
    authz = MemoryAuthzAdapter()
    embedder = MockEmbedderAdapter(dimension=16)
    reranker = MockRerankerAdapter()
    dlq = MemoryDLQAdapter()

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    return CoreState(
        retrieval_pipeline=pipeline,
        authz=authz,
        vector_store=vector_store,
        dlq=dlq,
    )


@pytest.mark.asyncio
async def test_health_and_readiness_endpoints(test_state: CoreState) -> None:
    app = create_app(test_state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Liveness probes
        resp_health = await client.get("/health")
        assert resp_health.status_code == 200
        assert resp_health.json()["status"] == "ok"

        resp_healthz = await client.get("/healthz")
        assert resp_healthz.status_code == 200

        resp_api_health = await client.get("/api/v1/health")
        assert resp_api_health.status_code == 200

        # Readiness probes
        resp_ready = await client.get("/readiness")
        assert resp_ready.status_code == 200
        data = resp_ready.json()
        assert data["status"] == "ready"
        assert data["checks"]["vector_store"] == "ok (in-memory)"
        assert data["checks"]["authz"] == "ok"
        assert data["checks"]["embedder"] == "ok"
        assert data["checks"]["reranker"] == "ok"

        resp_readyz = await client.get("/readyz")
        assert resp_readyz.status_code == 200

        resp_api_readiness = await client.get("/api/v1/readiness")
        assert resp_api_readiness.status_code == 200


@pytest.mark.asyncio
async def test_readiness_probe_fails_when_dependency_unhealthy(test_state: CoreState) -> None:
    # Inject failure into authz bulk_check
    with patch.object(
        test_state.authz,
        "bulk_check",
        new=AsyncMock(side_effect=RuntimeError("SpiceDB connection refused")),
    ):
        app = create_app(test_state)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get("/readiness")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "unhealthy"
            assert "SpiceDB connection refused" in data["checks"]["authz"]


@pytest.mark.asyncio
async def test_dlq_api_endpoints(test_state: CoreState) -> None:
    app = create_app(test_state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Seed an item in DLQ
        item = await test_state.dlq.enqueue(
            connector_id="linear",
            resource_id="issue_404",
            error_message="Graphql timeout",
            payload={"ticket": "LIN-404"},
        )

        # GET /api/v1/dlq
        resp_list = await client.get("/api/v1/dlq")
        assert resp_list.status_code == 200
        body = resp_list.json()
        assert body["total"] == 1
        assert body["items"][0]["resource_id"] == "issue_404"

        # POST /api/v1/dlq/{item_id}/retry
        resp_retry = await client.post(f"/api/v1/dlq/{item.id}/retry")
        assert resp_retry.status_code == 200
        assert resp_retry.json()["status"] == "retried"
        assert resp_retry.json()["item"]["retry_count"] == 1

        # DELETE /api/v1/dlq/{item_id}
        resp_del = await client.delete(f"/api/v1/dlq/{item.id}")
        assert resp_del.status_code == 200
        assert resp_del.json()["status"] == "deleted"

        # Retry non-existent item -> 404
        resp_not_found = await client.post("/api/v1/dlq/non_existent_id/retry")
        assert resp_not_found.status_code == 404
