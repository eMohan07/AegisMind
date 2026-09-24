from __future__ import annotations

import httpx
import pytest
from aegismind_infra.secrets import EnvelopeEncryptionEngine, MemorySecretStore

from aegismind_core.app import create_app
from aegismind_core.routes import CoreState


@pytest.mark.asyncio
async def test_secrets_endpoints_with_envelope() -> None:
    # Use real AES-GCM envelope encryption backend for SecretStore
    engine = EnvelopeEncryptionEngine()
    secret_store = MemorySecretStore(engine=engine)

    state = CoreState(secret_store=secret_store)
    app = create_app(state)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Store a secret
        payload = {
            "name": "jira_api_key",
            "secret_value": "super_secret_token_12345",
            "tenant_id": "tenant_prod",
        }
        resp = await client.post("/api/v1/secrets", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"status": "stored", "name": "jira_api_key"}

        # 2. Retrieve the secret
        get_resp = await client.get("/api/v1/secrets/jira_api_key")
        assert get_resp.status_code == 200
        assert get_resp.json() == {"name": "jira_api_key", "value": "super_secret_token_12345"}

        # 3. Verify ciphertext in envelope store is truly encrypted
        stored_entry = secret_store._store.get("jira_api_key")
        assert stored_entry is not None
        assert "super_secret_token_12345" not in stored_entry.ciphertext

        # 4. Unknown secret returns 404
        not_found_resp = await client.get("/api/v1/secrets/nonexistent")
        assert not_found_resp.status_code == 404

        # 5. Check audit entry was generated
        audit_resp = await client.get("/api/v1/audit?event_type=security")
        assert audit_resp.status_code == 200
        audit_data = audit_resp.json()
        assert audit_data["total"] >= 1
        assert audit_data["entries"][0]["resource_id"] == "jira_api_key"
