from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aegismind_adapters.authz_spicedb import (
    AEGISMIND_SPICEDB_SCHEMA,
    SpiceDBAuthzAdapter,
)
from aegismind_core.domain.permissions import (
    ConsistencyRequirement,
    ConsistencyToken,
    PermissionCheck,
    Resource,
    Subject,
)


def test_spicedb_schema_definitions() -> None:
    assert "definition user" in AEGISMIND_SPICEDB_SCHEMA
    assert "definition folder" in AEGISMIND_SPICEDB_SCHEMA
    assert "definition document" in AEGISMIND_SPICEDB_SCHEMA
    assert "permission view = reader + writer + folder->view" in AEGISMIND_SPICEDB_SCHEMA


@pytest.mark.asyncio
async def test_spicedb_uninitialized_client_raises() -> None:
    adapter = SpiceDBAuthzAdapter(auto_connect=False)
    assert adapter._client is None

    check = PermissionCheck(
        subject=Subject(type="user", id="alice"),
        permission="view",
        resource=Resource(type="document", id="doc_1"),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await adapter.check(check)
    assert "SpiceDB client is not available" in str(exc_info.value)


@pytest.mark.asyncio
async def test_spicedb_adapter_with_mocked_client() -> None:
    mock_client = MagicMock()

    # Mock response pair
    pair_allowed = MagicMock()
    pair_allowed.item.permissionship = 1  # PERMISSIONSHIP_HAS_PERMISSION

    pair_denied = MagicMock()
    pair_denied.item.permissionship = 2  # PERMISSIONSHIP_NO_PERMISSION

    mock_response = MagicMock()
    mock_response.pairs = [pair_allowed, pair_denied]

    mock_client.permissions_service.CheckBulkPermissions.return_value = mock_response

    adapter = SpiceDBAuthzAdapter(client=mock_client)

    checks = [
        PermissionCheck(
            subject=Subject(type="user", id="alice"),
            permission="view",
            resource=Resource(type="document", id="doc_1"),
        ),
        PermissionCheck(
            subject=Subject(type="user", id="alice"),
            permission="view",
            resource=Resource(type="document", id="doc_2"),
        ),
    ]

    decisions = await adapter.bulk_check(
        checks=checks,
        consistency=ConsistencyToken(requirement=ConsistencyRequirement.AT_LEAST_AS_FRESH),
    )

    assert len(decisions) == 2
    assert decisions[0].permitted
    assert not decisions[1].permitted
    mock_client.permissions_service.CheckBulkPermissions.assert_called_once()
