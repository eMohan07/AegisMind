from __future__ import annotations

import logging

from aegismind_infra.ports import SecretStorePort
from aegismind_infra.secrets.envelope import EnvelopeCiphertext, EnvelopeEncryptionEngine

logger = logging.getLogger(__name__)


class MemorySecretStore(SecretStorePort):
    """In-memory fake secret store implementing envelope encryption."""

    def __init__(
        self,
        engine: EnvelopeEncryptionEngine | None = None,
    ) -> None:
        self.engine = engine or EnvelopeEncryptionEngine()
        self._store: dict[str, EnvelopeCiphertext] = {}

    def _format_key(self, key: str, tenant_id: str | None) -> str:
        return f"{tenant_id}:{key}" if tenant_id else key

    async def get_secret(self, key: str, tenant_id: str | None = None) -> str | None:
        """Retrieve and decrypt secret value."""
        storage_key = self._format_key(key, tenant_id)
        envelope = self._store.get(storage_key)
        if envelope is None:
            return None
        return self.engine.decrypt_str(envelope)

    async def set_secret(self, key: str, value: str, tenant_id: str | None = None) -> None:
        """Encrypt and store secret under key."""
        storage_key = self._format_key(key, tenant_id)
        envelope = self.engine.encrypt(value)
        self._store[storage_key] = envelope

    async def delete_secret(self, key: str, tenant_id: str | None = None) -> bool:
        """Delete secret by key."""
        storage_key = self._format_key(key, tenant_id)
        return self._store.pop(storage_key, None) is not None

    def get_envelope(self, key: str, tenant_id: str | None = None) -> EnvelopeCiphertext | None:
        """Direct access to raw envelope ciphertext for inspection or testing."""
        storage_key = self._format_key(key, tenant_id)
        return self._store.get(storage_key)
