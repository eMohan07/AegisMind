from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from aegismind_connector_sdk.ports import ConnectorPort, ConnectorSpec
from aegismind_connector_sdk.verify.harness import assert_conforms
from aegismind_types import ACL, Record


class ConformingMemoryConnector(ConnectorPort):
    """Reference in-memory connector satisfying all conformance rules."""

    def __init__(self, records: list[Record] | None = None) -> None:
        now = datetime.now(UTC)
        self._records = records or [
            Record(
                id="doc_01",
                source="memory_source",
                external_id="ext_01",
                payload={"title": "Test Document", "status": "active"},
                acl=ACL(allowed_principals=["user:alice"], is_public=False),
                created_at=now,
                updated_at=now,
            ),
            Record(
                id="doc_02",
                source="memory_source",
                external_id="ext_02",
                payload={"title": "Deleted Page", "deleted": True},
                acl=ACL(is_public=True),
                created_at=now,
                updated_at=now,
            ),
        ]

    def spec(self) -> ConnectorSpec:
        return ConnectorSpec(
            name="memory_source",
            version="1.0.0",
            supports_incremental=True,
            supported_destination_sync_modes=["full_refresh", "incremental"],
        )

    async def check(self) -> bool:
        return True

    async def read(
        self,
        state: dict[str, Any] | None = None,
    ) -> AsyncIterator[Record]:
        for r in self._records:
            yield r


class NonConformingConnector(ConnectorPort):
    """Broken connector with empty spec name and failing check."""

    def spec(self) -> ConnectorSpec:
        return ConnectorSpec(name="", version="0.1")

    async def check(self) -> bool:
        return False

    async def read(
        self,
        state: dict[str, Any] | None = None,
    ) -> AsyncIterator[Record]:
        if False:
            yield Record(
                id="none",
                source="none",
                external_id="none",
                payload={},
                acl=ACL(),
            )


@pytest.mark.asyncio
async def test_assert_conforms_success() -> None:
    connector = ConformingMemoryConnector()
    # Conformance assertion should pass smoothly
    await assert_conforms(connector)


@pytest.mark.asyncio
async def test_assert_conforms_empty_name_fails() -> None:
    broken = NonConformingConnector()
    with pytest.raises(AssertionError) as exc_info:
        await assert_conforms(broken)
    assert "non-empty string" in str(exc_info.value)
