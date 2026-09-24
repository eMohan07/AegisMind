from __future__ import annotations

import logging
from typing import Any

from aegismind_types import Principal

from aegismind_identity.ports import IdentityPort

logger = logging.getLogger(__name__)


class DatabaseIdentityAdapter(IdentityPort):
    """Builtin database store adapter for persistent user identities and memberships."""

    def __init__(
        self,
        db_pool: Any | None = None,
        table_prefix: str = "aegismind_id_",
    ) -> None:
        self.db_pool = db_pool
        self.table_prefix = table_prefix
        # In-memory backing tables when standalone or testing without live database
        self._users: dict[str, Principal] = {}
        self._groups: dict[str, set[str]] = {}
        self._tenant_scopes: dict[str, set[str]] = {}

    def upsert_user(
        self,
        principal: Principal,
        groups: list[str] | None = None,
        tenant_scopes: list[str] | None = None,
    ) -> None:
        """Upsert a user record in the identity database."""
        self._users[principal.id] = principal
        if groups is not None:
            self._groups[principal.id] = set(groups)
        if tenant_scopes is not None:
            self._tenant_scopes[principal.id] = set(tenant_scopes)
        elif principal.tenant_id:
            if principal.id not in self._tenant_scopes:
                self._tenant_scopes[principal.id] = set()
            self._tenant_scopes[principal.id].add(principal.tenant_id)

    async def resolve_principal(
        self,
        token_or_id: str,
        tenant_id: str | None = None,
    ) -> Principal:
        """Resolve a principal from the database store."""
        if self.db_pool is not None:
            query = (
                f"SELECT id, type, tenant_id, attributes "  # noqa: S608
                f"FROM {self.table_prefix}users WHERE id = $1"
            )
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, token_or_id)
                if row:
                    return Principal(
                        id=row["id"],
                        type=row["type"],
                        tenant_id=row["tenant_id"] or tenant_id,
                        attributes=row["attributes"] or {},
                    )

        principal = self._users.get(token_or_id)
        if principal:
            if tenant_id and not principal.tenant_id:
                return Principal(
                    id=principal.id,
                    type=principal.type,
                    tenant_id=tenant_id,
                    attributes=principal.attributes,
                )
            return principal

        # Fallback for unrecognized principal
        return Principal(
            id=token_or_id,
            type="user",
            tenant_id=tenant_id,
            attributes={},
        )

    async def get_groups(
        self,
        principal_id: str,
        tenant_id: str | None = None,
    ) -> list[str]:
        """Resolve all assigned groups for the principal from the database."""
        if self.db_pool is not None:
            query = (
                f"SELECT group_name FROM {self.table_prefix}groups "  # noqa: S608
                f"WHERE principal_id = $1"
            )
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, principal_id)
                return sorted(r["group_name"] for r in rows)

        groups = set(self._groups.get(principal_id, set()))
        principal = self._users.get(principal_id)
        if principal and "groups" in principal.attributes:
            attr_groups = principal.attributes["groups"]
            if isinstance(attr_groups, list):
                groups.update(str(g) for g in attr_groups)
        return sorted(groups)

    async def get_tenant_scopes(
        self,
        principal_id: str,
    ) -> list[str]:
        """Resolve all accessible tenant scopes for the principal."""
        if self.db_pool is not None:
            query = (
                f"SELECT tenant_id FROM {self.table_prefix}tenants "  # noqa: S608
                f"WHERE principal_id = $1"
            )
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, principal_id)
                return sorted(r["tenant_id"] for r in rows)

        scopes = set(self._tenant_scopes.get(principal_id, set()))
        principal = self._users.get(principal_id)
        if principal and principal.tenant_id:
            scopes.add(principal.tenant_id)
        return sorted(scopes)
