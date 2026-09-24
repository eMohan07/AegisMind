from __future__ import annotations

import logging

from aegismind_types import ACL, Principal

from aegismind_authz.ports import RelationshipTuple

logger = logging.getLogger(__name__)


def encode_subject(
    principal: Principal | str,
    domain_mappings: dict[str, str] | None = None,
) -> str:
    """Encode a Principal or string identifier into canonical Zanzibar subject notation.

    Examples:
        Principal(id="alice", type="user") -> "user:alice"
        Principal(id="engineers", type="group") -> "group:engineers#member"
        "bob@acme.com" -> "user:bob@acme.com" (or transformed via domain_mappings)
    """
    if isinstance(principal, Principal):
        if principal.type == "group":
            return f"group:{principal.id}#member"
        return f"{principal.type}:{principal.id}"

    raw = principal.strip()

    # Check for existing relation notation
    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        if prefix == "group" and "#" not in rest:
            return f"group:{rest}#member"
        return raw

    # Handle email addresses with domain mapping
    if "@" in raw:
        username, domain = raw.split("@", 1)
        if domain_mappings and domain in domain_mappings:
            target_domain = domain_mappings[domain]
            return f"user:{username}@{target_domain}"
        return f"user:{raw}"

    # Default fallback to user
    return f"user:{raw}"


def decode_subject(subject_str: str) -> tuple[str, str, str | None]:
    """Decode a canonical Zanzibar subject string into (type, id, relation).

    Examples:
        "user:alice" -> ("user", "alice", None)
        "group:eng#member" -> ("group", "eng", "member")
    """
    if ":" not in subject_str:
        return "user", subject_str, None

    subj_type, rest = subject_str.split(":", 1)
    if "#" in rest:
        subj_id, relation = rest.split("#", 1)
        return subj_type, subj_id, relation

    return subj_type, rest, None


def acl_to_relationship_tuples(
    resource_id: str,
    acl: ACL,
    resource_type: str = "document",
    default_relation: str = "viewer",
    group_aliases: dict[str, list[str]] | None = None,
    domain_mappings: dict[str, str] | None = None,
) -> list[RelationshipTuple]:
    """Convert connector-provided source ACL into canonical Zanzibar relationship tuples.

    Handles viewer, editor, and owner relations, expands group aliases,
    and applies domain mappings.
    """
    canonical_resource = resource_id if ":" in resource_id else f"{resource_type}:{resource_id}"

    tuples: list[RelationshipTuple] = []
    seen: set[tuple[str, str, str]] = set()

    # Public access is mapped to user:* viewer relation
    if acl.is_public:
        pub_tuple = RelationshipTuple(
            resource=canonical_resource,
            relation="viewer",
            subject="user:*",
        )
        tuples.append(pub_tuple)
        seen.add((pub_tuple.resource, pub_tuple.relation, pub_tuple.subject))

    # Process allowed principals
    for raw_principal in acl.allowed_principals:
        # Determine relation from prefix if embedded (e.g. "editor:user:alice")
        relation = default_relation
        target = raw_principal

        if target.startswith("owner:"):
            relation = "owner"
            target = target.removeprefix("owner:")
        elif target.startswith("editor:"):
            relation = "editor"
            target = target.removeprefix("editor:")
        elif target.startswith("viewer:"):
            relation = "viewer"
            target = target.removeprefix("viewer:")

        # Check for group alias expansion
        expanded_targets = [target]
        clean_target = target.removeprefix("group:").removesuffix("#member")
        if group_aliases and clean_target in group_aliases:
            expanded_targets = [f"group:{alias}#member" for alias in group_aliases[clean_target]]

        for exp_target in expanded_targets:
            subj = encode_subject(exp_target, domain_mappings=domain_mappings)
            key = (canonical_resource, relation, subj)
            if key not in seen:
                seen.add(key)
                tuples.append(
                    RelationshipTuple(
                        resource=canonical_resource,
                        relation=relation,
                        subject=subj,
                    )
                )

    return tuples
