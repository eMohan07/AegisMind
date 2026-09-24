from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AuthSpec(BaseModel):
    """Authentication specification for declarative connectors."""

    model_config = ConfigDict(frozen=True)

    type: Literal["none", "api_key", "bearer", "basic"] = Field(
        default="none",
        description="Authentication mechanism",
    )
    header_name: str = Field(
        default="Authorization",
        description="Header name when using api_key auth",
    )
    token_env_var: str | None = Field(
        default=None,
        description="Environment variable name providing auth token",
    )
    token: str | None = Field(
        default=None,
        description="Static or injected auth token",
    )
    username: str | None = None
    password: str | None = None


class PaginationSpec(BaseModel):
    """Pagination strategy and parameters."""

    model_config = ConfigDict(frozen=True)

    type: Literal["none", "cursor", "page_number", "offset"] = Field(
        default="none",
        description="Pagination method",
    )
    page_size: int = Field(default=50, ge=1, description="Number of items requested per page")
    cursor_param: str = Field(default="cursor", description="Query param name for cursor")
    next_cursor_path: str | None = Field(
        default="next_cursor",
        description="JSONPath expression pointing to next cursor string in response",
    )
    page_param: str = Field(default="page", description="Query param name for page number")
    offset_param: str = Field(default="offset", description="Query param name for item offset")
    limit_param: str = Field(default="limit", description="Query param name for page size")


class CursorSpec(BaseModel):
    """Incremental sync cursor extraction specification."""

    model_config = ConfigDict(frozen=True)

    cursor_field: str = Field(
        ...,
        description="Field path in record indicating update time or version, e.g. updated_at",
    )
    state_field: str = Field(
        default="cursor",
        description="Key name stored in connector state dictionary",
    )
    initial_value: Any | None = Field(
        default=None,
        description="Default initial cursor value when state is absent",
    )


class AclMappingSpec(BaseModel):
    """Specification for mapping response fields to canonical ACLs."""

    model_config = ConfigDict(frozen=True)

    allowed_principals_path: str | None = Field(
        default=None,
        description="JSONPath to allowed principal identifiers",
    )
    denied_principals_path: str | None = Field(
        default=None,
        description="JSONPath to denied principal identifiers",
    )
    is_public_path: str | None = Field(
        default=None,
        description="JSONPath to boolean is_public flag",
    )
    default_public: bool = Field(
        default=False,
        description="Default is_public flag if field is absent",
    )
    static_allowed: list[str] = Field(
        default_factory=list,
        description="Static principals automatically granted access to all records",
    )


class EndpointSpec(BaseModel):
    """HTTP endpoint specification."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(..., description="API endpoint path relative to base_url")
    method: Literal["GET", "POST"] = Field(default="GET", description="HTTP method")
    params: dict[str, Any] = Field(default_factory=dict, description="Default query parameters")
    headers: dict[str, str] = Field(default_factory=dict, description="Default HTTP headers")
    records_path: str = Field(
        default="records",
        description="JSONPath pointing to list of records in response payload",
    )


class ManifestSpec(BaseModel):
    """Complete declarative connector manifest specification."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Unique connector name identifier")
    version: str = Field(default="0.0.1", description="Connector manifest version")
    description: str = Field(
        default="",
        description="Human readable description of source system",
    )
    base_url: str = Field(..., description="Base API URL for the source service")
    endpoint: EndpointSpec = Field(..., description="Primary data extraction endpoint")
    auth: AuthSpec = Field(default_factory=AuthSpec, description="Authentication settings")
    pagination: PaginationSpec = Field(
        default_factory=PaginationSpec,
        description="Pagination strategy",
    )
    cursor: CursorSpec | None = Field(
        default=None,
        description="Optional incremental sync cursor configuration",
    )
    acl_mapping: AclMappingSpec = Field(
        default_factory=AclMappingSpec,
        description="Mapping rules for record ACL extraction",
    )
    id_path: str = Field(default="id", description="JSONPath to unique record id")
    external_id_path: str = Field(
        default="external_id",
        description="JSONPath to external source identifier",
    )
