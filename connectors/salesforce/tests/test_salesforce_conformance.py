from __future__ import annotations

import pytest
from aegismind_connector_salesforce import SalesforceConnector, get_connector
from aegismind_connector_sdk.verify import assert_conforms


@pytest.mark.asyncio
async def test_salesforce_conformance() -> None:
    connector = get_connector()
    await assert_conforms(connector, sample_state={"last_updated_at": "2026-09-01T00:00:00Z"})


@pytest.mark.asyncio
async def test_salesforce_acl_extraction() -> None:
    connector = SalesforceConnector()
    records = []
    async for record in connector.read():
        records.append(record)

    assert len(records) > 0
    for r in records:
        assert r.source == "salesforce"
        assert r.acl is not None
        assert isinstance(r.acl.allowed_principals, list)
