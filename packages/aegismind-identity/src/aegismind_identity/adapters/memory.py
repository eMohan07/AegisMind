from __future__ import annotations

import logging

from aegismind_types import Principal

from aegismind_identity.ports import IdentityPort

logger = logging.getLogger(__name__)


class MemoryIdentityAdapter(IdentityPort):
    """In-memory identity provider adapter for tests and local development."""

    def __init__(self) -> None:
        self._principals: dict[str, Principal] = {}
        self._groups: dict[str, set[str]] = {}
        self._tenant_scopes: dict[str, set[str]] = {}

    def add_principal(
        self,
        principal: Principal,
        groups: list[str] | None = None,
        tenant_scopes: list[str] | None = None,
    ) -> None:
        """Register or seed a principal in the memory adapter."""
        self._principals[principal.id] = principal
        if groups:
            if principal.id not in self._groups:
                self._groups[principal.id] = set()
            self._groups[principal.id].update(groups)
        if tenant_scopes:
            if principal.id not in self._tenant_scopes:
                self._tenant_scopes[principal.id] = set()
            self._tenant_scopes[principal.id].update(tenant_scopes)
        elif principal.tenant_id:
            if principal.id not in self._tenant_scopes:
                self._tenant_scopes[principal.id] = set()
            self._tenant_scopes[principal.id].add(principal.tenant_id)

    async def resolve_principal(
        self,
        token_or_id: str,
        tenant_id: str | None = None,
    ) -> Principal:
        """Resolve a principal by ID or token string."""
        principal = self._principals.get(token_or_id)
        if principal is not None:
            # If explicit tenant_id provided and principal has no tenant, assign it
            if tenant_id and not principal.tenant_id:
                return Principal(
                    id=principal.id,
                    type=principal.type,
                    tenant_id=tenant_id,
                    attributes=principal.attributes,
                )
            return principal

        # Fallback dynamic resolution
        return Principal(
            id=token_or_id,
            type="user",
            tenant_id=tenant_id,
            attributes={"groups": list(self._groups.get(token_or_id, set()))},
        )

    async def get_groups(
        self,
        principal_id: str,
        tenant_id: str | None = None,
    ) -> list[str]:
        """Resolve all group memberships for a principal."""
        groups = set(self._groups.get(principal_id, set()))
        principal = self._principals.get(principal_id)
        if principal and "groups" in principal.attributes:
            attr_groups = principal.attributes["groups"]
            if isinstance(attr_groups, list):
                groups.update(str(g) for g in attr_groups)
        return sorted(groups)

    async def get_tenant_scopes(
        self,
        principal_id: str,
    ) -> list[str]:
        """Resolve all accessible tenant scopes for a principal."""
        scopes = set(self._tenant_scopes.get(principal_id, set()))
        principal = self._principals.get(principal_id)
        if principal and principal.tenant_id:
            scopes.add(principal.tenant_id)
        return sorted(scopes)
