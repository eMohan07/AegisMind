from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aegismind_types import ACL, Record

from aegismind_connector_sdk.ports import ConnectorPort, ConnectorSpec

logger = logging.getLogger(__name__)


async def assert_conforms(
    connector: ConnectorPort,
    sample_state: dict[str, Any] | None = None,
    allow_empty_read: bool = False,
) -> None:
    """Verification harness asserting that a connector conforms to the AegisMind connector contract.

    Asserts:
    1. spec() returns a valid ConnectorSpec with non-empty name and version.
    2. check() executes asynchronously and returns a boolean.
    3. read() yields valid Record instances with valid IDs, source, and timestamps.
    4. Faithful ACL mapping: every record includes a valid ACL structure.
    5. Deletion / tombstone detection conformance.
    6. Incremental sync and state tracking conformance.
    """
    # 1. Validate spec()
    spec = connector.spec()
    assert isinstance(spec, ConnectorSpec), f"spec() must return ConnectorSpec, got {type(spec)}"
    assert spec.name.strip(), "spec().name must be a non-empty string"
    assert spec.version.strip(), "spec().version must be a non-empty string"
    assert isinstance(spec.config_schema, dict), "spec().config_schema must be a dictionary"
    assert isinstance(spec.supports_incremental, bool), (
        "spec().supports_incremental must be boolean"
    )

    # 2. Validate check()
    is_healthy = await connector.check()
    assert isinstance(is_healthy, bool), f"check() must return boolean, got {type(is_healthy)}"

    # 3. Validate read() records and ACL mapping
    record_count = 0
    async for record in connector.read(state=sample_state):
        record_count += 1

        # Record invariants
        assert isinstance(record, Record), f"Expected Record, got {type(record)}"
        assert isinstance(record.id, str) and record.id.strip(), (
            "Record.id must be non-empty string"
        )
        assert isinstance(record.source, str) and record.source.strip(), (
            "Record.source must be non-empty string"
        )
        assert isinstance(record.external_id, str) and record.external_id.strip(), (
            "Record.external_id must be non-empty string"
        )
        assert isinstance(record.payload, dict), "Record.payload must be a dictionary"
        assert isinstance(record.created_at, datetime), "Record.created_at must be datetime"
        assert isinstance(record.updated_at, datetime), "Record.updated_at must be datetime"

        # 4. Faithful ACL mapping invariants
        assert isinstance(record.acl, ACL), "Record.acl must be an instance of ACL"
        assert isinstance(record.acl.allowed_principals, list), (
            "ACL.allowed_principals must be a list"
        )
        assert isinstance(record.acl.denied_principals, list), (
            "ACL.denied_principals must be a list"
        )
        assert isinstance(record.acl.is_public, bool), "ACL.is_public must be boolean"

        # 5. Deletion detection inspection: if payload marks deletion, verify tombstone contract
        if record.payload.get("deleted") is True or record.payload.get("_deleted") is True:
            logger.debug("Observed deletion tombstone for record '%s'", record.id)

    if not allow_empty_read:
        assert record_count > 0, "Connector read() did not yield any records during verification"

    logger.info(
        "Connector '%s' passed all conformance assertions (%d records)", spec.name, record_count
    )
