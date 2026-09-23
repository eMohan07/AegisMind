from __future__ import annotations

import pytest

from aegismind_adapters.authz_memory import MemoryAuthzAdapter
from aegismind_core.domain.permissions import (
    ConsistencyRequirement,
    ConsistencyToken,
    PermissionCheck,
    Resource,
    Subject,
)


@pytest.mark.asyncio
async def test_direct_document_permissions() -> None:
    adapter = MemoryAuthzAdapter()

    user_alice = Subject(type="user", id="alice")
    user_bob = Subject(type="user", id="bob")
    doc_1 = Resource(type="document", id="doc_1")

    # Initially nobody has access
    decision_alice = await adapter.check(
        PermissionCheck(subject=user_alice, permission="view", resource=doc_1)
    )
    assert not decision_alice.permitted

    # Grant Alice reader permission
    token = await adapter.write_relationship(
        subject=user_alice,
        relation="reader",
        resource=doc_1,
    )
    assert token is not None

    # Now Alice has view permission, Bob does not
    dec_alice = await adapter.check(
        PermissionCheck(subject=user_alice, permission="view", resource=doc_1)
    )
    dec_bob = await adapter.check(
        PermissionCheck(subject=user_bob, permission="view", resource=doc_1)
    )

    assert dec_alice.permitted
    assert not dec_bob.permitted


@pytest.mark.asyncio
async def test_writer_implies_view() -> None:
    adapter = MemoryAuthzAdapter()
    user_alice = Subject(type="user", id="alice")
    doc_1 = Resource(type="document", id="doc_1")

    await adapter.write_relationship(
        subject=user_alice,
        relation="writer",
        resource=doc_1,
    )

    view_dec = await adapter.check(
        PermissionCheck(subject=user_alice, permission="view", resource=doc_1)
    )
    edit_dec = await adapter.check(
        PermissionCheck(subject=user_alice, permission="edit", resource=doc_1)
    )

    assert view_dec.permitted
    assert edit_dec.permitted


@pytest.mark.asyncio
async def test_folder_hierarchy_inheritance() -> None:
    adapter = MemoryAuthzAdapter()
    user_alice = Subject(type="user", id="alice")
    folder_sec = Resource(type="folder", id="security")
    doc_vault = Resource(type="document", id="doc_vault")

    # Document belongs to folder
    await adapter.write_relationship(
        subject=Subject(type="folder", id="security"),
        relation="folder",
        resource=doc_vault,
    )

    # Alice is reader of folder
    await adapter.write_relationship(
        subject=user_alice,
        relation="reader",
        resource=folder_sec,
    )

    # Alice should inherit view permission on doc_vault
    decision = await adapter.check(
        PermissionCheck(subject=user_alice, permission="view", resource=doc_vault)
    )
    assert decision.permitted


@pytest.mark.asyncio
async def test_bulk_check_and_wildcard() -> None:
    adapter = MemoryAuthzAdapter()
    user_alice = Subject(type="user", id="alice")
    user_bob = Subject(type="user", id="bob")
    doc_public = Resource(type="document", id="doc_public")
    doc_private = Resource(type="document", id="doc_private")

    # Public document has wildcard reader
    await adapter.write_relationship(
        subject=Subject(type="user", id="*"),
        relation="reader",
        resource=doc_public,
    )

    # Private document is only for Alice
    await adapter.write_relationship(
        subject=user_alice,
        relation="reader",
        resource=doc_private,
    )

    checks = [
        PermissionCheck(subject=user_bob, permission="view", resource=doc_public),
        PermissionCheck(subject=user_bob, permission="view", resource=doc_private),
    ]

    consistency = ConsistencyToken(requirement=ConsistencyRequirement.AT_LEAST_AS_FRESH)
    decisions = await adapter.bulk_check(checks, consistency=consistency)

    assert len(decisions) == 2
    assert decisions[0].permitted  # Bob can view public document via wildcard
    assert not decisions[1].permitted  # Bob cannot view Alice's private document
