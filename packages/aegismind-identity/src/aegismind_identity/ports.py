from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aegismind_types import Principal
from pydantic import BaseModel, ConfigDict, Field


class UserProfile(BaseModel):
    """User profile data normalized from identity provider claims."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique subject identifier")
    username: str = Field(..., description="Preferred username or login handle")
    email: str | None = Field(default=None, description="Primary email address")
    name: str | None = Field(default=None, description="Full display name")
    tenant_id: str | None = Field(default=None, description="Primary tenant identifier")
    groups: list[str] = Field(default_factory=list, description="Assigned group memberships")
    roles: list[str] = Field(default_factory=list, description="Assigned roles or entitlements")
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific extended attributes",
    )


@runtime_checkable
class IdentityPort(Protocol):
    """Port for identity resolution, group memberships, and tenant scopes."""

    async def resolve_principal(
        self,
        token_or_id: str,
        tenant_id: str | None = None,
    ) -> Principal:
        """Resolve an authentication token or identifier into a canonical Principal."""
        ...

    async def get_groups(
        self,
        principal_id: str,
        tenant_id: str | None = None,
    ) -> list[str]:
        """Resolve all group memberships for a principal."""
        ...

    async def get_tenant_scopes(
        self,
        principal_id: str,
    ) -> list[str]:
        """Resolve all accessible tenant scopes for a principal."""
        ...
