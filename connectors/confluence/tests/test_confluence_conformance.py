from __future__ import annotations

import pytest
from aegismind_connector_confluence import ConfluenceConnector, get_connector
from aegismind_connector_sdk.verify import assert_conforms


@pytest.mark.asyncio
async def test_confluence_conformance() -> None:
    connector = get_connector()
    await assert_conforms(connector, sample_state={"last_updated_at": "2026-09-01T00:00:00Z"})


@pytest.mark.asyncio
async def test_confluence_acl_extraction() -> None:
    connector = ConfluenceConnector()
    records = []
    async for record in connector.read():
        records.append(record)

    assert len(records) > 0
    for r in records:
        assert r.source == "confluence"
        assert r.acl is not None
        assert isinstance(r.acl.allowed_principals, list)
