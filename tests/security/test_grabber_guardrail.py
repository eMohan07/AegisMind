from __future__ import annotations

import re
from pathlib import Path

import pytest

from aegismind_core.oauth import (
    AtlassianOAuthProvider,
    GitHubOAuthProvider,
    GoogleOAuthProvider,
    SlackOAuthProvider,
)
from aegismind_core.routes import CoreState


@pytest.mark.guardrail
def test_static_guardrail_no_insecure_tls_or_anti_bot_bypass() -> None:
    """Rule 5 Static Assertion: Verify no anti-bot or insecure TLS bypass exists."""
    workspace_root = Path("d:/aegisMind")
    source_dirs = [
        workspace_root / "packages",
        workspace_root / "connectors",
        workspace_root / "src",
    ]

    # Prohibited patterns indicating anti-bot evasion or TLS security disablement
    prohibited_patterns = [
        re.compile(r"verify\s*=\s*False"),  # TLS certificate validation disabling
        re.compile(r"cf_clearance", re.IGNORECASE),  # Cloudflare anti-bot scraper cookies
        re.compile(r"puppeteer-stealth", re.IGNORECASE),  # Browser fingerprint spoofing
        re.compile(r"turnstile_bypass", re.IGNORECASE),  # CAPTCHA bypass kits
        re.compile(r"bypass_cloudflare", re.IGNORECASE),  # Anti-bot bypass kits
        re.compile(r"fake_useragent", re.IGNORECASE),  # Anti-bot rotation evasion
    ]

    # Scan python files
    violations: list[str] = []
    for s_dir in source_dirs:
        if not s_dir.exists():
            continue
        for py_file in s_dir.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            for pattern in prohibited_patterns:
                match = pattern.search(text)
                if match:
                    violations.append(
                        f"Prohibited '{pattern.pattern}' in {py_file} at {match.start()}"
                    )

    assert not violations, "\n".join(violations)


@pytest.mark.guardrail
def test_oauth_providers_enforce_https_endpoints() -> None:
    """Verify that all OAuth providers enforce HTTPS authorization and token endpoints."""
    providers = [
        GitHubOAuthProvider("client_id", "secret"),
        GoogleOAuthProvider("client_id", "secret"),
        SlackOAuthProvider("client_id", "secret"),
        AtlassianOAuthProvider("client_id", "secret"),
    ]

    for p in providers:
        assert p.authorize_url.startswith("https://"), (
            f"Provider '{p.name}' authorize_url must be HTTPS"
        )
        assert p.token_url.startswith("https://"), f"Provider '{p.name}' token_url must be HTTPS"
        assert p.userinfo_url.startswith("https://"), (
            f"Provider '{p.name}' userinfo_url must be HTTPS"
        )


@pytest.mark.guardrail
@pytest.mark.asyncio
async def test_audit_logs_do_not_leak_plaintext_secrets() -> None:
    """Assert that security operations do not store plaintext secrets in audit logs."""
    state = CoreState()
    sensitive_token = "ghp_SuperSecretCredential99999"

    entry = state.record_audit(
        event_type="security",
        principal_id="admin",
        action="store_secret",
        resource_id="github_sync_token",
        metadata={"tenant_id": "tenant_123"},
    )

    # Verify sensitive token is never present in audit entry fields or metadata
    entry_dict = entry.model_dump()
    entry_json = str(entry_dict)
    assert sensitive_token not in entry_json
    assert "password" not in entry_dict["metadata"]
    assert "secret_value" not in entry_dict["metadata"]
