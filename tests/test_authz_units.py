from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.adapters.openfga import OpenFGAAuthzAdapter
from aegismind_authz.ports import CheckRequest, RelationshipTuple
from aegismind_types import Principal, TokenConsistency


@pytest.mark.asyncio
async def test_memory_adapter_write_and_check() -> None:
    adapter = MemoryAuthzAdapter()
    alice = Principal(id="alice", type="user")
    bob = Principal(id="bob", type="user")

    # Grant Alice viewer permission on document:doc_100
    token = await adapter.write_tuples(
        [
            RelationshipTuple(
                resource="document:doc_100",
                relation="viewer",
                subject="user:alice",
            )
        ]
    )
    assert token.at_least_as_fresh
    assert token.token is not None

    # Check permission
    assert await adapter.check_permission(alice, "viewer", "document:doc_100")
    assert not await adapter.check_permission(bob, "viewer", "document:doc_100")


@pytest.mark.asyncio
async def test_memory_adapter_wildcard_access() -> None:
    adapter = MemoryAuthzAdapter()
    charlie = Principal(id="charlie", type="user")

    await adapter.write_tuples(
        [
            RelationshipTuple(
                resource="document:public_doc",
                relation="viewer",
                subject="user:*",
            )
        ]
    )

    assert await adapter.check_permission(charlie, "viewer", "document:public_doc")
    assert await adapter.check_permission(charlie, "view", "document:public_doc")


@pytest.mark.asyncio
async def test_memory_adapter_group_inheritance() -> None:
    adapter = MemoryAuthzAdapter()
    alice = Principal(id="alice", type="user")
    bob = Principal(id="bob", type="user")

    # Document allows group:engineers#member as viewer
    # Alice is member of group:engineers
    # Bob is member of group:marketing
    await adapter.write_tuples(
        [
            RelationshipTuple(
                resource="document:design_spec",
                relation="viewer",
                subject="group:engineers#member",
            ),
            RelationshipTuple(
                resource="group:engineers",
                relation="member",
                subject="user:alice",
            ),
            RelationshipTuple(
                resource="group:marketing",
                relation="member",
                subject="user:bob",
            ),
        ]
    )

    assert await adapter.check_permission(alice, "viewer", "document:design_spec")
    assert not await adapter.check_permission(bob, "viewer", "document:design_spec")


@pytest.mark.asyncio
async def test_memory_adapter_folder_hierarchy_inheritance() -> None:
    adapter = MemoryAuthzAdapter()
    alice = Principal(id="alice", type="user")

    # Document belongs to folder
    # Alice is reader of folder
    await adapter.write_tuples(
        [
            RelationshipTuple(
                resource="folder:sec_folder",
                relation="folder",
                subject="document:vault_doc",
            ),
            RelationshipTuple(
                resource="folder:sec_folder",
                relation="reader",
                subject="user:alice",
            ),
        ]
    )

    assert await adapter.check_permission(alice, "view", "document:vault_doc")


@pytest.mark.asyncio
async def test_memory_adapter_delete_tuples() -> None:
    adapter = MemoryAuthzAdapter()
    alice = Principal(id="alice", type="user")
    t = RelationshipTuple(
        resource="document:doc_temp",
        relation="viewer",
        subject="user:alice",
    )

    await adapter.write_tuples([t])
    assert await adapter.check_permission(alice, "viewer", "document:doc_temp")

    del_token = await adapter.delete_tuples([t])
    assert del_token.at_least_as_fresh
    assert not await adapter.check_permission(alice, "viewer", "document:doc_temp")


@pytest.mark.asyncio
async def test_memory_adapter_bulk_check() -> None:
    adapter = MemoryAuthzAdapter()
    await adapter.write_tuples(
        [
            RelationshipTuple(
                resource="document:d1",
                relation="viewer",
                subject="user:alice",
            ),
            RelationshipTuple(
                resource="document:d2",
                relation="editor",
                subject="user:alice",
            ),
        ]
    )

    requests = [
        CheckRequest(resource="document:d1", permission="viewer", subject="user:alice"),
        CheckRequest(resource="document:d2", permission="editor", subject="user:alice"),
        CheckRequest(resource="document:d1", permission="editor", subject="user:alice"),
        CheckRequest(resource="document:d3", permission="viewer", subject="user:alice"),
    ]

    consistency = TokenConsistency(at_least_as_fresh=True)
    decisions = await adapter.bulk_check(requests, consistency=consistency)
    assert decisions == [True, True, False, False]


@pytest.mark.asyncio
async def test_openfga_adapter_mocked_calls() -> None:
    mock_client = MagicMock()
    mock_res_allowed = MagicMock()
    mock_res_allowed.allowed = True
    mock_client.check.return_value = mock_res_allowed

    adapter = OpenFGAAuthzAdapter(client=mock_client)
    alice = Principal(id="alice", type="user")

    res = await adapter.check_permission(alice, "viewer", "document:doc_1")
    assert res is True
    mock_client.check.assert_called_once_with(
        user="user:alice",
        relation="viewer",
        object="document:doc_1",
    )

    # Test write_tuples
    await adapter.write_tuples(
        [RelationshipTuple(resource="doc:1", relation="viewer", subject="user:alice")]
    )
    mock_client.write.assert_called_once()
