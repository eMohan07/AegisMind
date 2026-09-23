from __future__ import annotations

import logging

from aegismind_core.domain.permissions import (
    AuthzDecision,
    ConsistencyRequirement,
    ConsistencyToken,
    PermissionCheck,
    Resource,
    Subject,
)
from aegismind_core.ports.authz import AuthzPort

logger = logging.getLogger(__name__)


class MemoryAuthzAdapter(AuthzPort):
    """In-memory Zanzibar-inspired authorization adapter.

    Supports direct relationships, folder hierarchy inheritance,
    wildcards, and revision token tracking.
    """

    def __init__(self) -> None:
        # Tuple store: set of (subject_key, relation, resource_key)
        self._tuples: set[tuple[str, str, str]] = set()
        self._revision: int = 1
        logger.debug("Initialized MemoryAuthzAdapter")

    def _make_subject_key(self, subject: Subject) -> str:
        return subject.to_string()

    def _make_resource_key(self, resource: Resource) -> str:
        return resource.to_string()

    async def write_relationship(
        self,
        subject: Subject,
        relation: str,
        resource: Resource,
    ) -> str:
        s_key = self._make_subject_key(subject)
        r_key = self._make_resource_key(resource)
        self._tuples.add((s_key, relation, r_key))
        self._revision += 1
        token = str(self._revision)
        logger.debug(
            "Wrote tuple (%s, %s, %s), new zed token: %s",
            s_key,
            relation,
            r_key,
            token,
        )
        return token

    async def delete_relationship(
        self,
        subject: Subject,
        relation: str,
        resource: Resource,
    ) -> str:
        s_key = self._make_subject_key(subject)
        r_key = self._make_resource_key(resource)
        self._tuples.discard((s_key, relation, r_key))
        self._revision += 1
        token = str(self._revision)
        logger.debug(
            "Deleted tuple (%s, %s, %s), new zed token: %s",
            s_key,
            relation,
            r_key,
            token,
        )
        return token

    async def check(
        self,
        check: PermissionCheck,
        consistency: ConsistencyToken | None = None,
    ) -> AuthzDecision:
        results = await self.bulk_check([check], consistency)
        return results[0]

    async def bulk_check(
        self,
        checks: list[PermissionCheck],
        consistency: ConsistencyToken | None = None,
    ) -> list[AuthzDecision]:
        req = consistency.requirement if consistency else ConsistencyRequirement.AT_LEAST_AS_FRESH
        token = consistency.token if consistency else None
        logger.debug(
            "Executing bulk_check for %d items at consistency=%s, token=%s",
            len(checks),
            req,
            token,
        )

        decisions: list[AuthzDecision] = []
        for item in checks:
            is_permitted = self._evaluate_permission(
                subject=item.subject,
                permission=item.permission,
                resource=item.resource,
            )
            decisions.append(
                AuthzDecision(
                    permitted=is_permitted,
                    reason="Allowed by policy" if is_permitted else "Access denied",
                )
            )

        return decisions

    def _has_relation(self, subject_key: str, relation: str, resource_key: str) -> bool:
        return (subject_key, relation, resource_key) in self._tuples

    def _evaluate_permission(
        self,
        subject: Subject,
        permission: str,
        resource: Resource,
        visited: set[str] | None = None,
    ) -> bool:
        if visited is None:
            visited = set()

        call_sig = f"{subject.to_string()}->{permission}@{resource.to_string()}"
        if call_sig in visited:
            return False
        visited.add(call_sig)

        s_key = self._make_subject_key(subject)
        r_key = self._make_resource_key(resource)
        wildcard_key = f"{subject.type}:*"

        # 1. Direct permission or relation match
        if self._has_relation(s_key, permission, r_key) or self._has_relation(
            wildcard_key, permission, r_key
        ):
            return True

        # 2. Zanzibar permission expansion for document: view = reader + writer + folder->view
        if resource.type == "document" and permission == "view":
            if (
                self._has_relation(s_key, "reader", r_key)
                or self._has_relation(wildcard_key, "reader", r_key)
                or self._has_relation(s_key, "writer", r_key)
                or self._has_relation(wildcard_key, "writer", r_key)
            ):
                return True

            # Check folder inheritance: document -> folder
            for s, rel, r in self._tuples:
                if rel == "folder" and r == r_key:
                    folder_res = Resource(type="folder", id=s.split(":", 1)[1])
                    if self._evaluate_permission(subject, "view", folder_res, visited):
                        return True

        # 3. Zanzibar permission expansion for document: edit = writer + folder->edit
        if resource.type == "document" and permission == "edit":
            if self._has_relation(s_key, "writer", r_key) or self._has_relation(
                wildcard_key, "writer", r_key
            ):
                return True

            for s, rel, r in self._tuples:
                if rel == "folder" and r == r_key:
                    folder_res = Resource(type="folder", id=s.split(":", 1)[1])
                    if self._evaluate_permission(subject, "edit", folder_res, visited):
                        return True

        # 4. Folder permissions: view = reader + writer; edit = writer
        if resource.type == "folder" and permission == "view":
            if (
                self._has_relation(s_key, "reader", r_key)
                or self._has_relation(wildcard_key, "reader", r_key)
                or self._has_relation(s_key, "writer", r_key)
                or self._has_relation(wildcard_key, "writer", r_key)
            ):
                return True

        if resource.type == "folder" and permission == "edit":
            if self._has_relation(s_key, "writer", r_key) or self._has_relation(
                wildcard_key, "writer", r_key
            ):
                return True

        return False
