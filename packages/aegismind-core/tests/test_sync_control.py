from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from aegismind_connector_sdk.ports import ConnectorPort, ConnectorSpec
from aegismind_ingestion.ports import IngestionPipelinePort, IngestionSummary
from aegismind_types import ACL, Record

from aegismind_core.app import create_app
from aegismind_core.routes import CoreState


class MockConnector(ConnectorPort):
    def __init__(self, name: str = "mock_jira", records: list[Record] | None = None) -> None:
        self.name = name
        self.records = records or []

    def spec(self) -> ConnectorSpec:
        return ConnectorSpec(
            name=self.name,
            version="1.0.0",
            description="Mock connector for testing sync control",
            supported_auth=["bearer"],
        )

    async def check(self) -> bool:
        return True

    async def read(self, state: dict[str, Any] | None = None) -> AsyncIterator[Record]:
        for rec in self.records:
            yield rec


class MockIngestionPipeline(IngestionPipelinePort):
    def __init__(self) -> None:
        self.ingested_records: list[Record] = []

    async def ingest_records(self, records: list[Record]) -> IngestionSummary:
        self.ingested_records.extend(records)
        return IngestionSummary(
            total_records=len(records),
            chunks_indexed=len(records) * 2,
            tuples_written=len(records),
            errors=[],
        )


@pytest.mark.asyncio
async def test_connector_spec_discovery_and_configuration() -> None:
    ingestion = MockIngestionPipeline()
    state = CoreState(ingestion_pipeline=ingestion)
    mock_conn = MockConnector("jira_tickets")
    state.connectors["jira_tickets"] = mock_conn

    app = create_app(state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Spec discovery
        list_resp = await client.get("/api/v1/connectors")
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert len(data["connectors"]) == 1
        assert data["connectors"][0]["name"] == "jira_tickets"
        assert data["connectors"][0]["spec"]["version"] == "1.0.0"

        # 2. Configure connector
        config_resp = await client.post(
            "/api/v1/connectors",
            json={
                "connector_name": "jira_tickets",
                "action": "configure",
                "config": {"site_url": "https://company.atlassian.net"},
            },
        )
        assert config_resp.status_code == 200
        assert config_resp.json() == {"status": "configured", "connector": "jira_tickets"}


@pytest.mark.asyncio
async def test_sync_trigger_and_cursor_tracking() -> None:
    sample_records = [
        Record(
            id="rec_1",
            source="jira",
            external_id="PROJ-101",
            payload={"summary": "Fix auth vulnerability"},
            acl=ACL(allowed_principals=["user:alice"]),
            updated_at=datetime.now(UTC),
        ),
        Record(
            id="rec_2",
            source="jira",
            external_id="PROJ-102",
            payload={"summary": "Deploy zero trust mesh"},
            acl=ACL(allowed_principals=["user:bob"]),
            updated_at=datetime.now(UTC),
        ),
    ]

    ingestion = MockIngestionPipeline()
    state = CoreState(ingestion_pipeline=ingestion)
    mock_conn = MockConnector("jira_tickets", records=sample_records)
    state.connectors["jira_tickets"] = mock_conn

    app = create_app(state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        sync_resp = await client.post(
            "/api/v1/connectors",
            json={
                "connector_name": "jira_tickets",
                "action": "sync",
                "initial_cursor": {"page": 1},
            },
        )
        assert sync_resp.status_code == 200
        report = sync_resp.json()["report"]
        assert report["status"] == "COMPLETED"
        assert report["records_synced"] == 2
        assert report["chunks_indexed"] == 4
        assert report["tuples_written"] == 2
        assert report["final_cursor"]["last_record_id"] == "rec_2"

        # Verify ingestion pipeline received the records
        assert len(ingestion.ingested_records) == 2

        # Verify audit log recorded sync trigger
        audit_resp = await client.get("/api/v1/audit?event_type=connector")
        assert audit_resp.status_code == 200
        audit_data = audit_resp.json()
        assert audit_data["total"] >= 1


@pytest.mark.asyncio
async def test_sync_unknown_connector_error() -> None:
    state = CoreState()
    app = create_app(state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/connectors",
            json={"connector_name": "nonexistent", "action": "sync"},
        )
        assert resp.status_code == 404
