from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx
from aegismind_types import Principal

from aegismind_identity.normalizer import OIDCClaimNormalizer
from aegismind_identity.ports import IdentityPort

logger = logging.getLogger(__name__)


class OidcIdentityAdapter(IdentityPort):
    """OIDC identity adapter supporting Zitadel, Keycloak, and generic OIDC providers."""

    def __init__(
        self,
        provider: str = "auto",
        issuer_url: str | None = None,
        userinfo_endpoint: str | None = None,
        client_id: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider = provider
        self.issuer_url = issuer_url.rstrip("/") if issuer_url else None
        self.userinfo_endpoint = userinfo_endpoint
        self.client_id = client_id
        self._client = client
        self._cached_principals: dict[str, Principal] = {}

    def decode_token_payload(self, token: str) -> dict[str, Any]:
        """Decode unverified JWT claims from compact token string.

        Used for local claim extraction when full cryptographic validation
        is performed at the API gateway or reverse proxy boundary.
        """
        parts = token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            padded = payload_b64 + "=" * (-len(payload_b64) % 4)
            try:
                raw_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
                data = json.loads(raw_bytes.decode("utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as exc:
                logger.debug("Failed to decode token as JWT payload: %s", exc)
        return {}

    async def _fetch_userinfo(self, token: str) -> dict[str, Any]:
        """Fetch userinfo claims from the OIDC userinfo endpoint."""
        endpoint = self.userinfo_endpoint
        if not endpoint and self.issuer_url:
            endpoint = f"{self.issuer_url}/protocol/openid-connect/userinfo"
        if not endpoint:
            return {}

        headers = {"Authorization": f"Bearer {token}"}
        if self._client is not None:
            resp = await self._client.get(endpoint, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}

        async with httpx.AsyncClient() as client:
            resp = await client.get(endpoint, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}

    async def resolve_principal(
        self,
        token_or_id: str,
        tenant_id: str | None = None,
    ) -> Principal:
        """Resolve a JWT bearer token or subject identifier into a normalized Principal."""
        # 1. Try decoding token payload directly
        claims = self.decode_token_payload(token_or_id)

        # 2. If token is opaque and userinfo endpoint is available, fetch claims
        if not claims and self.userinfo_endpoint:
            try:
                claims = await self._fetch_userinfo(token_or_id)
            except Exception as exc:
                logger.warning("Failed fetching userinfo for opaque token: %s", exc)

        # 3. If still no claims, treat token_or_id as subject ID
        if not claims:
            claims = {"sub": token_or_id}

        principal = OIDCClaimNormalizer.normalize(
            claims=claims,
            provider=self.provider,
            tenant_id=tenant_id,
        )
        self._cached_principals[principal.id] = principal
        return principal

    async def get_groups(
        self,
        principal_id: str,
        tenant_id: str | None = None,
    ) -> list[str]:
        """Extract group memberships from cached principal attributes."""
        principal = self._cached_principals.get(principal_id)
        if principal and "groups" in principal.attributes:
            groups = principal.attributes["groups"]
            if isinstance(groups, list):
                return sorted(str(g) for g in groups)
        return []

    async def get_tenant_scopes(
        self,
        principal_id: str,
    ) -> list[str]:
        """Extract accessible tenant scopes from cached principal attributes."""
        principal = self._cached_principals.get(principal_id)
        if principal and principal.tenant_id:
            return [principal.tenant_id]
        return []
