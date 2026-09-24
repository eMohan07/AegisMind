from __future__ import annotations

import pytest
from aegismind_connector_granola import GranolaConnector, get_connector
from aegismind_connector_sdk.verify import assert_conforms


@pytest.mark.asyncio
async def test_granola_conformance() -> None:
    connector = get_connector()
    await assert_conforms(connector, sample_state={"last_updated_at": "2026-09-01T00:00:00Z"})


@pytest.mark.asyncio
async def test_granola_acl_extraction() -> None:
    connector = GranolaConnector()
    records = []
    async for record in connector.read():
        records.append(record)

    assert len(records) > 0
    for r in records:
        assert r.source == "granola"
        assert r.acl is not None
        assert isinstance(r.acl.allowed_principals, list)
