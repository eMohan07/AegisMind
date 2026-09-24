from __future__ import annotations

import httpx
import pytest

from aegismind_core.oauth import (
    AtlassianOAuthProvider,
    GitHubOAuthProvider,
    GoogleOAuthProvider,
    OAuthToken,
    OAuthUserInfo,
    SlackOAuthProvider,
    get_oauth_provider,
)


def test_provider_factory() -> None:
    github = get_oauth_provider("github", "gh_id", "gh_sec")
    assert isinstance(github, GitHubOAuthProvider)
    assert github.client_id == "gh_id"

    google = get_oauth_provider("google", "goog_id", "goog_sec")
    assert isinstance(google, GoogleOAuthProvider)

    slack = get_oauth_provider("slack", "slk_id", "slk_sec")
    assert isinstance(slack, SlackOAuthProvider)

    atlassian = get_oauth_provider("atlassian", "atl_id", "atl_sec")
    assert isinstance(atlassian, AtlassianOAuthProvider)

    with pytest.raises(ValueError, match="Unsupported OAuth provider"):
        get_oauth_provider("unknown_idp", "id", "sec")


def test_github_auth_url() -> None:
    provider = GitHubOAuthProvider(client_id="gh_client", client_secret="gh_secret")
    url = provider.get_authorization_url(
        redirect_uri="https://app.aegismind.io/callback",
        state="xyz123",
    )
    assert "https://github.com/login/oauth/authorize" in url
    assert "client_id=gh_client" in url
    assert "state=xyz123" in url
    assert "redirect_uri=https%3A%2F%2Fapp.aegismind.io%2Fcallback" in url


@pytest.mark.asyncio
async def test_github_exchange_code_and_userinfo() -> None:
    provider = GitHubOAuthProvider(client_id="gh_client", client_secret="gh_secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(
                200,
                json={
                    "access_token": "gho_mock_token_123",
                    "token_type": "Bearer",
                    "scope": "read:user user:email",
                },
            )
        if request.url.path == "/user":
            return httpx.Response(
                200,
                json={
                    "id": 123456,
                    "login": "octocat",
                    "name": "Mona Lisa Octocat",
                    "email": "octocat@github.com",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        token: OAuthToken = await provider.exchange_code(
            code="code_123",
            redirect_uri="https://app.aegismind.io/callback",
            http_client=client,
        )
        assert token.access_token == "gho_mock_token_123"
        assert token.token_type == "Bearer"

        userinfo: OAuthUserInfo = await provider.get_user_info(
            access_token=token.access_token,
            http_client=client,
        )
        assert userinfo.provider == "github"
        assert userinfo.subject_id == "123456"
        assert userinfo.name == "Mona Lisa Octocat"
        assert userinfo.email == "octocat@github.com"


@pytest.mark.asyncio
async def test_google_exchange_and_userinfo() -> None:
    provider = GoogleOAuthProvider(client_id="goog_client", client_secret="goog_secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.mock_token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "id_token": "jwt.mock.idtoken",
                },
            )
        if request.url.path == "/v1/userinfo":
            return httpx.Response(
                200,
                json={
                    "sub": "google-user-999",
                    "name": "Jane Doe",
                    "email": "jane@example.com",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        token = await provider.exchange_code(
            "code_goog", "https://app/callback", http_client=client
        )
        assert token.access_token == "ya29.mock_token"

        user = await provider.get_user_info(token.access_token, http_client=client)
        assert user.provider == "google"
        assert user.subject_id == "google-user-999"
        assert user.email == "jane@example.com"


@pytest.mark.asyncio
async def test_slack_exchange_and_userinfo() -> None:
    provider = SlackOAuthProvider(client_id="slk_client", client_secret="slk_secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/oauth.v2.access":
            return httpx.Response(
                200,
                json={
                    "access_token": "xoxp-mock-slack-token",
                    "token_type": "Bearer",
                },
            )
        if request.url.path == "/api/users.identity":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "user": {
                        "name": "Alex Smith",
                        "id": "U123456",
                        "email": "alex@company.slack.com",
                    },
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        token = await provider.exchange_code("code_slk", "https://app/callback", http_client=client)
        assert token.access_token == "xoxp-mock-slack-token"

        user = await provider.get_user_info(token.access_token, http_client=client)
        assert user.provider == "slack"
        assert user.subject_id == "U123456"
        assert user.email == "alex@company.slack.com"


@pytest.mark.asyncio
async def test_atlassian_flow() -> None:
    provider = AtlassianOAuthProvider(client_id="atl_client", client_secret="atl_secret")
    url = provider.get_authorization_url("https://app/callback", "state123")
    assert "audience=api.atlassian.com" in url
    assert "prompt=consent" in url

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "atl_mock_access_token",
                    "token_type": "Bearer",
                },
            )
        if request.url.path == "/me":
            return httpx.Response(
                200,
                json={
                    "account_id": "jira-acc-777",
                    "name": "Charlie Jira",
                    "email": "charlie@atlassian.net",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        token = await provider.exchange_code("code_atl", "https://app/callback", http_client=client)
        assert token.access_token == "atl_mock_access_token"

        user = await provider.get_user_info(token.access_token, http_client=client)
        assert user.provider == "atlassian"
        assert user.subject_id == "jira-acc-777"
        assert user.name == "Charlie Jira"
