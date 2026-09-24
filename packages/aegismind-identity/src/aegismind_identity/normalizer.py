from __future__ import annotations

import logging
from typing import Any

from aegismind_types import Principal

logger = logging.getLogger(__name__)


class OIDCClaimNormalizer:
    """Parser and normalizer for OIDC claims from Zitadel, Keycloak, and generic providers."""

    @staticmethod
    def detect_provider(claims: dict[str, Any]) -> str:
        """Infer the identity provider based on signature claim keys and issuer."""
        iss = str(claims.get("iss", "")).lower()
        if any(k.startswith("urn:zitadel:") for k in claims) or "zitadel" in iss:
            return "zitadel"
        if "realm_access" in claims or "resource_access" in claims:
            return "keycloak"
        return "generic"

    @classmethod
    def normalize_keycloak(
        cls,
        claims: dict[str, Any],
        tenant_id: str | None = None,
    ) -> Principal:
        """Parse Keycloak claims into a normalized Principal.

        Extracts roles from realm_access and resource_access, normalizes group paths,
        and extracts tenant scope.
        """
        sub = str(claims.get("sub", "")).strip()
        if not sub:
            msg = "Missing 'sub' claim in Keycloak token"
            raise ValueError(msg)

        # Collect roles
        roles: set[str] = set()
        realm_access = claims.get("realm_access")
        if isinstance(realm_access, dict):
            realm_roles = realm_access.get("roles", [])
            if isinstance(realm_roles, list):
                roles.update(str(r) for r in realm_roles)

        resource_access = claims.get("resource_access")
        if isinstance(resource_access, dict):
            for _client_name, client_data in resource_access.items():
                if isinstance(client_data, dict):
                    client_roles = client_data.get("roles", [])
                    if isinstance(client_roles, list):
                        roles.update(str(r) for r in client_roles)

        top_roles = claims.get("roles", [])
        if isinstance(top_roles, list):
            roles.update(str(r) for r in top_roles)

        # Collect and normalize groups (strip leading slashes)
        groups: list[str] = []
        raw_groups = claims.get("groups", [])
        if isinstance(raw_groups, list):
            for grp in raw_groups:
                clean_grp = str(grp).strip().lstrip("/")
                if clean_grp and clean_grp not in groups:
                    groups.append(clean_grp)

        # Resolve tenant ID
        resolved_tenant = (
            tenant_id or claims.get("tenant_id") or claims.get("org") or claims.get("organization")
        )
        if resolved_tenant is not None:
            resolved_tenant = str(resolved_tenant).strip()

        username = claims.get("preferred_username") or claims.get("username") or sub

        is_svc = "client_id" in claims and "preferred_username" not in claims
        principal_type = "service" if is_svc else "user"

        attributes: dict[str, Any] = {
            "email": claims.get("email"),
            "name": claims.get("name"),
            "username": username,
            "groups": groups,
            "roles": sorted(roles),
            "provider": "keycloak",
            "email_verified": claims.get("email_verified", False),
        }

        return Principal(
            id=sub,
            type=principal_type,
            tenant_id=resolved_tenant,
            attributes=attributes,
        )

    @classmethod
    def normalize_zitadel(
        cls,
        claims: dict[str, Any],
        tenant_id: str | None = None,
    ) -> Principal:
        """Parse Zitadel claims into a normalized Principal.

        Extracts organization ID from urn:zitadel:iam:org:id, project roles from
        urn:zitadel:iam:org:project:roles, and normalizes user attributes.
        """
        sub = str(claims.get("sub", "")).strip()
        if not sub:
            msg = "Missing 'sub' claim in Zitadel token"
            raise ValueError(msg)

        # Zitadel organization claim
        org_id = claims.get("urn:zitadel:iam:org:id")
        resolved_tenant = tenant_id or (str(org_id) if org_id is not None else None)

        # Project roles
        roles: set[str] = set()
        project_roles = claims.get("urn:zitadel:iam:org:project:roles")
        if isinstance(project_roles, dict):
            for _project_id, role_map in project_roles.items():
                if isinstance(role_map, dict):
                    for role_name in role_map:
                        roles.add(str(role_name))
                elif isinstance(role_map, list):
                    for role_name in role_map:
                        roles.add(str(role_name))

        raw_roles = claims.get("roles", [])
        if isinstance(raw_roles, list):
            roles.update(str(r) for r in raw_roles)

        # Groups / Teams
        groups: list[str] = []
        raw_groups = claims.get("groups", [])
        if isinstance(raw_groups, list):
            for grp in raw_groups:
                clean_grp = str(grp).strip().lstrip("/")
                if clean_grp and clean_grp not in groups:
                    groups.append(clean_grp)

        username = claims.get("preferred_username") or claims.get("username") or sub

        attributes: dict[str, Any] = {
            "email": claims.get("email"),
            "name": claims.get("name"),
            "username": username,
            "groups": groups,
            "roles": sorted(roles),
            "provider": "zitadel",
            "org_id": org_id,
            "primary_domain": claims.get("urn:zitadel:iam:org:domain:primary"),
            "email_verified": claims.get("email_verified", False),
        }

        return Principal(
            id=sub,
            type="user",
            tenant_id=resolved_tenant,
            attributes=attributes,
        )

    @classmethod
    def normalize_generic(
        cls,
        claims: dict[str, Any],
        tenant_id: str | None = None,
    ) -> Principal:
        """Parse standard generic OIDC claims into a normalized Principal."""
        sub = str(claims.get("sub", "")).strip()
        if not sub:
            msg = "Missing 'sub' claim in OIDC token"
            raise ValueError(msg)

        resolved_tenant = (
            tenant_id
            or claims.get("tenant_id")
            or claims.get("org_id")
            or claims.get("organization")
            or claims.get("tenant")
        )
        if resolved_tenant is not None:
            resolved_tenant = str(resolved_tenant).strip()

        groups: list[str] = []
        raw_groups = claims.get("groups", [])
        if isinstance(raw_groups, list):
            for grp in raw_groups:
                clean_grp = str(grp).strip().lstrip("/")
                if clean_grp and clean_grp not in groups:
                    groups.append(clean_grp)

        roles: list[str] = []
        raw_roles = claims.get("roles", [])
        if isinstance(raw_roles, list):
            roles = sorted(str(r) for r in raw_roles)

        username = (
            claims.get("preferred_username") or claims.get("username") or claims.get("email") or sub
        )

        principal_type = "service" if claims.get("client_id") and "email" not in claims else "user"

        attributes: dict[str, Any] = {
            "email": claims.get("email"),
            "name": claims.get("name"),
            "username": username,
            "groups": groups,
            "roles": roles,
            "provider": "generic",
            "email_verified": claims.get("email_verified", False),
        }

        return Principal(
            id=sub,
            type=principal_type,
            tenant_id=resolved_tenant,
            attributes=attributes,
        )

    @classmethod
    def normalize(
        cls,
        claims: dict[str, Any],
        provider: str = "auto",
        tenant_id: str | None = None,
    ) -> Principal:
        """Normalize claims using the specified or detected provider strategy."""
        selected_provider = cls.detect_provider(claims) if provider == "auto" else provider.lower()

        if selected_provider == "keycloak":
            return cls.normalize_keycloak(claims, tenant_id=tenant_id)
        if selected_provider == "zitadel":
            return cls.normalize_zitadel(claims, tenant_id=tenant_id)
        return cls.normalize_generic(claims, tenant_id=tenant_id)
