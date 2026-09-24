from __future__ import annotations

from aegismind_core.oauth.base import OAuthProvider, OAuthToken, OAuthUserInfo
from aegismind_core.oauth.providers import (
    AtlassianOAuthProvider,
    GitHubOAuthProvider,
    GoogleOAuthProvider,
    SlackOAuthProvider,
)


def get_oauth_provider(
    provider_name: str,
    client_id: str,
    client_secret: str,
    default_scope: str | None = None,
) -> OAuthProvider:
    """Factory helper to obtain an OAuth provider instance."""
    normalized = provider_name.strip().lower()
    if normalized == "github":
        return GitHubOAuthProvider(
            client_id=client_id,
            client_secret=client_secret,
            **({"default_scope": default_scope} if default_scope else {}),
        )
    if normalized == "google":
        return GoogleOAuthProvider(
            client_id=client_id,
            client_secret=client_secret,
            **({"default_scope": default_scope} if default_scope else {}),
        )
    if normalized == "slack":
        return SlackOAuthProvider(
            client_id=client_id,
            client_secret=client_secret,
            **({"default_scope": default_scope} if default_scope else {}),
        )
    if normalized == "atlassian":
        return AtlassianOAuthProvider(
            client_id=client_id,
            client_secret=client_secret,
            **({"default_scope": default_scope} if default_scope else {}),
        )
    raise ValueError(f"Unsupported OAuth provider: {provider_name}")


__all__ = [
    "AtlassianOAuthProvider",
    "GitHubOAuthProvider",
    "GoogleOAuthProvider",
    "OAuthProvider",
    "OAuthToken",
    "OAuthUserInfo",
    "SlackOAuthProvider",
    "get_oauth_provider",
]
