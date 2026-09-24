from __future__ import annotations

import logging
from typing import Any

import httpx

from aegismind_core.oauth.base import OAuthProvider, OAuthUserInfo

logger = logging.getLogger(__name__)


class GitHubOAuthProvider(OAuthProvider):
    """OAuth2 provider implementation for GitHub."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        default_scope: str = "read:user user:email",
    ) -> None:
        super().__init__(client_id, client_secret, default_scope)

    @property
    def name(self) -> str:
        return "github"

    @property
    def authorize_url(self) -> str:
        return "https://github.com/login/oauth/authorize"

    @property
    def token_url(self) -> str:
        return "https://github.com/login/oauth/access_token"

    @property
    def userinfo_url(self) -> str:
        return "https://api.github.com/user"

    async def get_user_info(
        self,
        access_token: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> OAuthUserInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "AegisMind-OAuth-Client",
        }
        should_close = False
        client = http_client
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            resp = await client.get(self.userinfo_url, headers=headers)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return OAuthUserInfo(
                provider="github",
                subject_id=str(data["id"]),
                email=data.get("email"),
                name=data.get("name") or data.get("login"),
                raw=data,
            )
        finally:
            if should_close:
                await client.aclose()


class GoogleOAuthProvider(OAuthProvider):
    """OAuth2 provider implementation for Google."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        default_scope: str = "openid email profile",
    ) -> None:
        super().__init__(client_id, client_secret, default_scope)

    @property
    def name(self) -> str:
        return "google"

    @property
    def authorize_url(self) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth"

    @property
    def token_url(self) -> str:
        return "https://oauth2.googleapis.com/token"

    @property
    def userinfo_url(self) -> str:
        return "https://openidconnect.googleapis.com/v1/userinfo"

    async def get_user_info(
        self,
        access_token: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> OAuthUserInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        should_close = False
        client = http_client
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            resp = await client.get(self.userinfo_url, headers=headers)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return OAuthUserInfo(
                provider="google",
                subject_id=str(data.get("sub", "")),
                email=data.get("email"),
                name=data.get("name"),
                raw=data,
            )
        finally:
            if should_close:
                await client.aclose()


class SlackOAuthProvider(OAuthProvider):
    """OAuth2 provider implementation for Slack."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        default_scope: str = "identity.basic identity.email",
    ) -> None:
        super().__init__(client_id, client_secret, default_scope)

    @property
    def name(self) -> str:
        return "slack"

    @property
    def authorize_url(self) -> str:
        return "https://slack.com/oauth/v2/authorize"

    @property
    def token_url(self) -> str:
        return "https://slack.com/api/oauth.v2.access"

    @property
    def userinfo_url(self) -> str:
        return "https://slack.com/api/users.identity"

    async def get_user_info(
        self,
        access_token: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> OAuthUserInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        should_close = False
        client = http_client
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            resp = await client.get(self.userinfo_url, headers=headers)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            user_info = data.get("user", {})
            sub = str(user_info.get("id") or data.get("sub", ""))
            return OAuthUserInfo(
                provider="slack",
                subject_id=sub,
                email=user_info.get("email") or data.get("email"),
                name=user_info.get("name") or data.get("name"),
                raw=data,
            )
        finally:
            if should_close:
                await client.aclose()


class AtlassianOAuthProvider(OAuthProvider):
    """OAuth2 provider implementation for Atlassian."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        default_scope: str = "read:me read:jira-user",
    ) -> None:
        super().__init__(client_id, client_secret, default_scope)

    @property
    def name(self) -> str:
        return "atlassian"

    @property
    def authorize_url(self) -> str:
        return "https://auth.atlassian.com/authorize"

    @property
    def token_url(self) -> str:
        return "https://auth.atlassian.com/oauth/token"

    @property
    def userinfo_url(self) -> str:
        return "https://api.atlassian.com/me"

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        scope: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        params = {
            "audience": "api.atlassian.com",
            "prompt": "consent",
        }
        if extra_params:
            params.update(extra_params)
        return super().get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            scope=scope,
            extra_params=params,
        )

    async def get_user_info(
        self,
        access_token: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> OAuthUserInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        should_close = False
        client = http_client
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            resp = await client.get(self.userinfo_url, headers=headers)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return OAuthUserInfo(
                provider="atlassian",
                subject_id=str(data.get("account_id", "")),
                email=data.get("email"),
                name=data.get("name"),
                raw=data,
            )
        finally:
            if should_close:
                await client.aclose()
