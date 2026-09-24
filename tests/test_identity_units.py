from __future__ import annotations

import base64
import json

import pytest
from aegismind_identity.adapters.db import DatabaseIdentityAdapter
from aegismind_identity.adapters.memory import MemoryIdentityAdapter
from aegismind_identity.adapters.oidc import OidcIdentityAdapter
from aegismind_identity.normalizer import OIDCClaimNormalizer
from aegismind_types import Principal


def test_keycloak_claim_parsing_and_normalization() -> None:
    claims = {
        "iss": "https://auth.corp.internal/realms/aegismind",
        "sub": "user-uuid-12345",
        "preferred_username": "alice",
        "email": "alice@corp.internal",
        "email_verified": True,
        "name": "Alice Smith",
        "realm_access": {"roles": ["default-roles-aegismind", "admin", "offline_access"]},
        "resource_access": {"aegismind-client": {"roles": ["editor", "viewer"]}},
        "groups": ["/engineering/platform", "/security/audit"],
        "tenant_id": "tenant-acme",
    }

    principal = OIDCClaimNormalizer.normalize_keycloak(claims)

    assert isinstance(principal, Principal)
    assert principal.id == "user-uuid-12345"
    assert principal.type == "user"
    assert principal.tenant_id == "tenant-acme"

    attrs = principal.attributes
    assert attrs["email"] == "alice@corp.internal"
    assert attrs["username"] == "alice"
    assert attrs["name"] == "Alice Smith"
    assert attrs["email_verified"] is True
    assert attrs["provider"] == "keycloak"

    # Verify normalized groups (leading slashes removed)
    assert attrs["groups"] == ["engineering/platform", "security/audit"]

    # Verify merged roles
    assert "admin" in attrs["roles"]
    assert "editor" in attrs["roles"]
    assert "viewer" in attrs["roles"]


def test_zitadel_claim_parsing_and_normalization() -> None:
    claims = {
        "iss": "https://issuer.zitadel.cloud",
        "sub": "zitadel-user-98765",
        "preferred_username": "bob",
        "email": "bob@zitadel.example.com",
        "email_verified": True,
        "name": "Bob Jones",
        "urn:zitadel:iam:org:id": "org-zitadel-456",
        "urn:zitadel:iam:org:domain:primary": "acme.com",
        "urn:zitadel:iam:org:project:roles": {
            "project-123": {
                "admin": {"org-zitadel-456": "acme.com"},
                "auditor": {"org-zitadel-456": "acme.com"},
            }
        },
        "groups": ["data-science", "analytics"],
    }

    principal = OIDCClaimNormalizer.normalize_zitadel(claims)

    assert isinstance(principal, Principal)
    assert principal.id == "zitadel-user-98765"
    assert principal.type == "user"
    assert principal.tenant_id == "org-zitadel-456"

    attrs = principal.attributes
    assert attrs["email"] == "bob@zitadel.example.com"
    assert attrs["username"] == "bob"
    assert attrs["name"] == "Bob Jones"
    assert attrs["provider"] == "zitadel"
    assert attrs["primary_domain"] == "acme.com"

    # Verify project roles extracted from Zitadel project roles map
    assert "admin" in attrs["roles"]
    assert "auditor" in attrs["roles"]
    assert attrs["groups"] == ["data-science", "analytics"]


def test_generic_oidc_claim_parsing_and_normalization() -> None:
    claims = {
        "iss": "https://accounts.example.org",
        "sub": "generic-subject-777",
        "email": "carol@example.org",
        "name": "Carol Danvers",
        "groups": ["/leadership", "management"],
        "roles": ["operator"],
        "organization": "tenant-omega",
    }

    principal = OIDCClaimNormalizer.normalize_generic(claims)

    assert isinstance(principal, Principal)
    assert principal.id == "generic-subject-777"
    assert principal.type == "user"
    assert principal.tenant_id == "tenant-omega"

    attrs = principal.attributes
    assert attrs["email"] == "carol@example.org"
    assert attrs["groups"] == ["leadership", "management"]
    assert attrs["roles"] == ["operator"]
    assert attrs["provider"] == "generic"


def test_provider_auto_detection() -> None:
    assert OIDCClaimNormalizer.detect_provider({"realm_access": {"roles": []}}) == "keycloak"
    assert OIDCClaimNormalizer.detect_provider({"urn:zitadel:iam:org:id": "123"}) == "zitadel"
    assert OIDCClaimNormalizer.detect_provider({"iss": "https://accounts.google.com"}) == "generic"


@pytest.mark.asyncio
async def test_oidc_adapter_jwt_payload_decoding() -> None:
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "iss": "https://auth.keycloak.local/realms/master",
        "sub": "usr_keycloak_99",
        "preferred_username": "dave",
        "email": "dave@corp.internal",
        "realm_access": {"roles": ["developer"]},
        "groups": ["engineers"],
        "tenant_id": "tenant-corp",
    }

    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    dummy_jwt = f"{h_b64}.{p_b64}.signature"

    adapter = OidcIdentityAdapter(provider="keycloak")
    principal = await adapter.resolve_principal(dummy_jwt)

    assert principal.id == "usr_keycloak_99"
    assert principal.tenant_id == "tenant-corp"
    assert principal.attributes["email"] == "dave@corp.internal"

    groups = await adapter.get_groups("usr_keycloak_99")
    assert groups == ["engineers"]

    scopes = await adapter.get_tenant_scopes("usr_keycloak_99")
    assert scopes == ["tenant-corp"]


@pytest.mark.asyncio
async def test_memory_identity_adapter_operations() -> None:
    adapter = MemoryIdentityAdapter()

    user = Principal(
        id="usr_admin",
        type="user",
        tenant_id="tenant_main",
        attributes={"email": "admin@aegismind.io"},
    )
    adapter.add_principal(
        principal=user,
        groups=["admins", "root"],
        tenant_scopes=["tenant_main", "tenant_backup"],
    )

    resolved = await adapter.resolve_principal("usr_admin")
    assert resolved.id == "usr_admin"
    assert resolved.tenant_id == "tenant_main"

    groups = await adapter.get_groups("usr_admin")
    assert groups == ["admins", "root"]

    scopes = await adapter.get_tenant_scopes("usr_admin")
    assert scopes == ["tenant_backup", "tenant_main"]


@pytest.mark.asyncio
async def test_database_identity_adapter_operations() -> None:
    adapter = DatabaseIdentityAdapter()

    user = Principal(
        id="usr_db_1",
        type="user",
        tenant_id="tenant_finance",
        attributes={"name": "Finance Admin", "groups": ["finance_lead"]},
    )
    adapter.upsert_user(
        principal=user,
        groups=["finance_lead", "auditors"],
        tenant_scopes=["tenant_finance"],
    )

    resolved = await adapter.resolve_principal("usr_db_1")
    assert resolved.id == "usr_db_1"
    assert resolved.tenant_id == "tenant_finance"

    groups = await adapter.get_groups("usr_db_1")
    assert groups == ["auditors", "finance_lead"]

    scopes = await adapter.get_tenant_scopes("usr_db_1")
    assert scopes == ["tenant_finance"]
