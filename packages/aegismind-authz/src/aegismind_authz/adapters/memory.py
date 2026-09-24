from __future__ import annotations

import logging

from aegismind_types import Principal, TokenConsistency

from aegismind_authz.mappers import decode_subject, encode_subject
from aegismind_authz.ports import AuthzPort, CheckRequest, RelationshipTuple

logger = logging.getLogger(__name__)


class MemoryAuthzAdapter(AuthzPort):
    """In-memory Zanzibar tuple store for fast, deterministic, hermetic tests."""

    def __init__(self) -> None:
        # Tuple storage: set of (resource, relation, subject)
        self._tuples: set[tuple[str, str, str]] = set()
        self._revision: int = 1
        logger.debug("Initialized MemoryAuthzAdapter")

    async def write_tuples(
        self,
        tuples: list[RelationshipTuple],
    ) -> TokenConsistency:
        for t in tuples:
            self._tuples.add((t.resource, t.relation, t.subject))
        self._revision += 1
        token = str(self._revision)
        logger.debug("Wrote %d tuples, new revision: %s", len(tuples), token)
        return TokenConsistency(token=token, at_least_as_fresh=True)

    async def delete_tuples(
        self,
        tuples: list[RelationshipTuple],
    ) -> TokenConsistency:
        for t in tuples:
            self._tuples.discard((t.resource, t.relation, t.subject))
        self._revision += 1
        token = str(self._revision)
        logger.debug("Deleted %d tuples, new revision: %s", len(tuples), token)
        return TokenConsistency(token=token, at_least_as_fresh=True)

    async def check_permission(
        self,
        subject: Principal,
        relation: str,
        resource: str,
    ) -> bool:
        subject_str = encode_subject(subject)
        req = CheckRequest(resource=resource, permission=relation, subject=subject_str)
        results = await self.bulk_check([req])
        return results[0]

    async def bulk_check(
        self,
        requests: list[CheckRequest],
        consistency: TokenConsistency | None = None,
    ) -> list[bool]:
        logger.debug(
            "Evaluating %d check requests at consistency token=%s",
            len(requests),
            consistency.token if consistency else None,
        )
        return [self._evaluate(req.subject, req.permission, req.resource) for req in requests]

    def _has_tuple(self, resource: str, relation: str, subject: str) -> bool:
        return (resource, relation, subject) in self._tuples

    def _evaluate(
        self,
        subject: str,
        permission: str,
        resource: str,
        visited: set[str] | None = None,
    ) -> bool:
        if visited is None:
            visited = set()

        sig = f"{subject}->{permission}@{resource}"
        if sig in visited:
            return False
        visited.add(sig)

        subj_type, _subj_id, _ = decode_subject(subject)
        wildcard_subject = f"{subj_type}:*"

        # 1. Direct tuple match
        if self._has_tuple(resource, permission, subject) or self._has_tuple(
            resource, permission, wildcard_subject
        ):
            return True

        # 2. Group membership resolution: check if subject belongs to any group holding relation
        for res, rel, grp_subj in self._tuples:
            if res == resource and (rel == permission or self._relation_implies(rel, permission)):
                # If tuple points to group:group_name#member
                if grp_subj.startswith("group:") and "#member" in grp_subj:
                    group_res = grp_subj.split("#", 1)[0]  # e.g. group:engineers
                    if self._has_tuple(group_res, "member", subject):
                        return True

        # 3. Document permission expansion
        # view = viewer + editor + owner + folder->view
        # edit = editor + owner + folder->edit
        res_type, _ = resource.split(":", 1) if ":" in resource else ("document", resource)

        if res_type == "document":
            if permission in ("view", "viewer"):
                for rel in ("viewer", "editor", "owner"):
                    if self._has_tuple(resource, rel, subject) or self._has_tuple(
                        resource, rel, wildcard_subject
                    ):
                        return True
                    # Check groups for rel
                    for res, r_rel, grp_subj in self._tuples:
                        if res == resource and r_rel == rel and grp_subj.startswith("group:"):
                            group_res = grp_subj.split("#", 1)[0]
                            if self._has_tuple(group_res, "member", subject):
                                return True

                # Check parent folder inheritance
                for p_res, rel, target_doc in self._tuples:
                    if rel == "folder" and target_doc == resource:
                        if self._evaluate(subject, "view", p_res, visited):
                            return True

            elif permission in ("edit", "editor"):
                for rel in ("editor", "owner"):
                    if self._has_tuple(resource, rel, subject) or self._has_tuple(
                        resource, rel, wildcard_subject
                    ):
                        return True
                    for res, r_rel, grp_subj in self._tuples:
                        if res == resource and r_rel == rel and grp_subj.startswith("group:"):
                            group_res = grp_subj.split("#", 1)[0]
                            if self._has_tuple(group_res, "member", subject):
                                return True

                for p_res, rel, target_doc in self._tuples:
                    if rel == "folder" and target_doc == resource:
                        if self._evaluate(subject, "edit", p_res, visited):
                            return True

        # 4. Folder permission expansion
        if res_type == "folder":
            if permission in ("view", "reader"):
                for rel in ("reader", "writer"):
                    if self._has_tuple(resource, rel, subject) or self._has_tuple(
                        resource, rel, wildcard_subject
                    ):
                        return True
            elif permission in ("edit", "writer"):
                if self._has_tuple(resource, "writer", subject) or self._has_tuple(
                    resource, "writer", wildcard_subject
                ):
                    return True

        return False

    def _relation_implies(self, tuple_rel: str, query_perm: str) -> bool:
        if tuple_rel == query_perm:
            return True
        if query_perm in ("view", "viewer") and tuple_rel in ("viewer", "editor", "owner"):
            return True
        if query_perm in ("edit", "editor") and tuple_rel in ("editor", "owner"):
            return True
        return False
