from __future__ import annotations

import pytest
from aegismind_connector_sdk.verify import assert_conforms
from aegismind_connector_sharepoint import SharePointConnector, get_connector


@pytest.mark.asyncio
async def test_sharepoint_conformance() -> None:
    connector = get_connector()
    await assert_conforms(connector, sample_state={"last_updated_at": "2026-09-01T00:00:00Z"})


@pytest.mark.asyncio
async def test_sharepoint_acl_extraction() -> None:
    connector = SharePointConnector()
    records = []
    async for record in connector.read():
        records.append(record)

    assert len(records) > 0
    for r in records:
        assert r.source == "sharepoint"
        assert r.acl is not None
        assert isinstance(r.acl.allowed_principals, list)
