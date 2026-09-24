from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aegismind_authz.adapters.spicedb import (
    AEGISMIND_ZED_SCHEMA,
    SpiceDBAuthzAdapter,
)
from aegismind_authz.mappers import decode_subject, encode_subject
from aegismind_authz.ports import CheckRequest, RelationshipTuple
from aegismind_types import Principal, TokenConsistency


def test_subject_encoding_principal() -> None:
    user_p = Principal(id="alice", type="user")
    assert encode_subject(user_p) == "user:alice"

    group_p = Principal(id="security", type="group")
    assert encode_subject(group_p) == "group:security#member"

    service_p = Principal(id="crawler", type="service")
    assert encode_subject(service_p) == "service:crawler"


def test_subject_encoding_string() -> None:
    assert encode_subject("alice") == "user:alice"
    assert encode_subject("user:alice") == "user:alice"
    assert encode_subject("group:eng") == "group:eng#member"
    assert encode_subject("group:eng#member") == "group:eng#member"
    assert encode_subject("bob@corp.com") == "user:bob@corp.com"

    # Domain mapping
    mapped = encode_subject("charlie@partner.io", domain_mappings={"partner.io": "partner_acme"})
    assert mapped == "user:charlie@partner_acme"


def test_subject_decoding() -> None:
    assert decode_subject("user:alice") == ("user", "alice", None)
    assert decode_subject("group:eng#member") == ("group", "eng", "member")
    assert decode_subject("standalone_id") == ("user", "standalone_id", None)


def test_zed_schema_definitions() -> None:
    assert "definition user" in AEGISMIND_ZED_SCHEMA
    assert "definition group" in AEGISMIND_ZED_SCHEMA
    assert "definition folder" in AEGISMIND_ZED_SCHEMA
    assert "definition document" in AEGISMIND_ZED_SCHEMA
    assert "permission view = viewer + editor + owner + folder->view" in AEGISMIND_ZED_SCHEMA


@pytest.mark.asyncio
async def test_spicedb_adapter_bulk_check_and_write_mocked() -> None:
    mock_client = MagicMock()

    # Mock response pairs for CheckBulkPermissions
    pair1 = MagicMock()
    pair1.item.permissionship = 1  # PERMISSIONSHIP_HAS_PERMISSION
    pair2 = MagicMock()
    pair2.item.permissionship = 2  # PERMISSIONSHIP_NO_PERMISSION

    mock_resp = MagicMock()
    mock_resp.pairs = [pair1, pair2]
    mock_client.permissions_service.CheckBulkPermissions.return_value = mock_resp

    # Mock WriteRelationships response
    write_resp = MagicMock()
    write_resp.written_at.token = "zed_token_test_123"
    mock_client.permissions_service.WriteRelationships.return_value = write_resp

    adapter = SpiceDBAuthzAdapter(client=mock_client)

    # 1. Test write_tuples
    token = await adapter.write_tuples(
        [
            RelationshipTuple(
                resource="document:doc_1",
                relation="viewer",
                subject="user:alice",
            )
        ]
    )
    assert token.token == "zed_token_test_123"
    assert token.at_least_as_fresh
    mock_client.permissions_service.WriteRelationships.assert_called_once()

    # 2. Test bulk_check
    requests = [
        CheckRequest(resource="document:doc_1", permission="view", subject="user:alice"),
        CheckRequest(resource="document:doc_2", permission="view", subject="user:alice"),
    ]
    results = await adapter.bulk_check(
        requests, consistency=TokenConsistency(token="zed_token_test_123")
    )
    assert results == [True, False]
    mock_client.permissions_service.CheckBulkPermissions.assert_called_once()
