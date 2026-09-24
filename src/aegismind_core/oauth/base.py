from __future__ import annotations

import logging
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class OAuthToken(BaseModel):
    """OAuth2 token payload returned by authorization server."""

    model_config = ConfigDict(frozen=True)

    access_token: str = Field(..., description="Bearer access token")
    token_type: str = Field(default="Bearer", description="Token type")
    refresh_token: str | None = Field(default=None, description="Optional refresh token")
    expires_in: int | None = Field(default=None, description="Lifetime in seconds")
    scope: str | None = Field(default=None, description="Granted scopes")
    id_token: str | None = Field(default=None, description="OpenID Connect ID token")


class OAuthUserInfo(BaseModel):
    """Normalized identity profile extracted from OAuth2 userinfo endpoint."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(..., description="Identity provider name")
    subject_id: str = Field(..., description="Unique subject identifier from provider")
    email: str | None = Field(default=None, description="User email address")
    name: str | None = Field(default=None, description="Full display name")
    raw: dict[str, Any] = Field(default_factory=dict, description="Raw provider claims")


class OAuthProvider(ABC):
    """Abstract base provider for OAuth2 authorization flows."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        default_scope: str = "",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.default_scope = default_scope

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the OAuth2 provider."""

    @property
    @abstractmethod
    def authorize_url(self) -> str:
        """URL for initiating user authorization."""

    @property
    @abstractmethod
    def token_url(self) -> str:
        """URL for code exchange and token retrieval."""

    @property
    @abstractmethod
    def userinfo_url(self) -> str:
        """URL for fetching authenticated user profile."""

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        scope: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Construct authorization URL for user redirect."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": scope or self.default_scope,
        }
        if extra_params:
            params.update(extra_params)
        return f"{self.authorize_url}?{urllib.parse.urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> OAuthToken:
        """Exchange authorization code for an access token."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        headers = {"Accept": "application/json"}

        should_close = False
        client = http_client
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            resp = await client.post(self.token_url, data=data, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
            return OAuthToken(
                access_token=payload["access_token"],
                token_type=payload.get("token_type", "Bearer"),
                refresh_token=payload.get("refresh_token"),
                expires_in=payload.get("expires_in"),
                scope=payload.get("scope"),
                id_token=payload.get("id_token"),
            )
        finally:
            if should_close:
                await client.aclose()

    @abstractmethod
    async def get_user_info(
        self,
        access_token: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> OAuthUserInfo:
        """Fetch and normalize user profile from provider userinfo endpoint."""
