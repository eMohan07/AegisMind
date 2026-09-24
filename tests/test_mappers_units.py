from __future__ import annotations

from aegismind_authz.mappers import acl_to_relationship_tuples
from aegismind_types import ACL


def test_acl_to_tuples_basic() -> None:
    acl = ACL(
        allowed_principals=["user:alice", "user:bob"],
        denied_principals=[],
        is_public=False,
    )
    tuples = acl_to_relationship_tuples("doc_101", acl)
    assert len(tuples) == 2
    assert tuples[0].resource == "document:doc_101"
    assert tuples[0].relation == "viewer"
    assert tuples[0].subject == "user:alice"
    assert tuples[1].subject == "user:bob"


def test_acl_to_tuples_with_roles() -> None:
    acl = ACL(
        allowed_principals=["viewer:user:alice", "editor:user:bob", "owner:user:carol"],
        is_public=False,
    )
    tuples = acl_to_relationship_tuples("doc_102", acl)
    assert len(tuples) == 3

    tuple_map = {t.subject: t.relation for t in tuples}
    assert tuple_map["user:alice"] == "viewer"
    assert tuple_map["user:bob"] == "editor"
    assert tuple_map["user:carol"] == "owner"


def test_acl_to_tuples_public_wildcard() -> None:
    acl = ACL(
        allowed_principals=["user:alice"],
        is_public=True,
    )
    tuples = acl_to_relationship_tuples("doc_public", acl)

    # Must contain both wildcard and specific user
    subjects = {t.subject for t in tuples}
    assert "user:*" in subjects
    assert "user:alice" in subjects


def test_acl_to_tuples_group_alias_expansion() -> None:
    acl = ACL(
        allowed_principals=["group:engineering"],
        is_public=False,
    )
    group_aliases = {
        "engineering": ["backend_team", "frontend_team", "platform_team"],
    }
    tuples = acl_to_relationship_tuples(
        "doc_team",
        acl,
        group_aliases=group_aliases,
    )

    subjects = {t.subject for t in tuples}
    assert subjects == {
        "group:backend_team#member",
        "group:frontend_team#member",
        "group:platform_team#member",
    }


def test_acl_to_tuples_domain_mapping() -> None:
    acl = ACL(
        allowed_principals=["alice@partner.com", "bob@corp.com"],
        is_public=False,
    )
    domain_mappings = {
        "partner.com": "partner_tenant.internal",
    }
    tuples = acl_to_relationship_tuples(
        "doc_cross_domain",
        acl,
        domain_mappings=domain_mappings,
    )

    subjects = {t.subject for t in tuples}
    assert "user:alice@partner_tenant.internal" in subjects
    assert "user:bob@corp.com" in subjects
