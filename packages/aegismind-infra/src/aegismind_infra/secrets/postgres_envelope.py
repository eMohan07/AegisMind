from __future__ import annotations

import logging
from typing import Any

from aegismind_infra.ports import SecretStorePort
from aegismind_infra.secrets.envelope import EnvelopeCiphertext, EnvelopeEncryptionEngine

logger = logging.getLogger(__name__)


class PostgresEnvelopeSecretStore(SecretStorePort):
    """Envelope-encrypted secret store for PostgreSQL database tables.

    Stores ciphertext, encrypted DEK, nonces, and KEK key ID in PostgreSQL rows.
    Supports in-place key rotation via DEK rewrapping.
    """

    def __init__(
        self,
        engine: EnvelopeEncryptionEngine | None = None,
        db_pool: Any | None = None,
        table_name: str = "aegismind_secrets",
    ) -> None:
        self.engine = engine or EnvelopeEncryptionEngine()
        self.db_pool = db_pool
        self.table_name = table_name
        # Fallback dictionary backing store when no live database pool is attached
        self._backing_store: dict[tuple[str | None, str], EnvelopeCiphertext] = {}

    async def get_secret(self, key: str, tenant_id: str | None = None) -> str | None:
        """Retrieve and decrypt secret value."""
        if self.db_pool is not None:
            # When db_pool is provided, execute SQL query
            query = (
                f"SELECT key_id, encrypted_dek, dek_nonce, ciphertext, nonce, algorithm "  # noqa: S608
                f"FROM {self.table_name} WHERE key = $1 "
                f"AND (tenant_id = $2 OR ($2 IS NULL AND tenant_id IS NULL))"
            )
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, key, tenant_id)
                if row is None:
                    return None
                envelope = EnvelopeCiphertext(
                    key_id=row["key_id"],
                    encrypted_dek=row["encrypted_dek"],
                    dek_nonce=row["dek_nonce"],
                    ciphertext=row["ciphertext"],
                    nonce=row["nonce"],
                    algorithm=row.get("algorithm", "AES-256-GCM"),
                )
                return self.engine.decrypt_str(envelope)

        storage_key = (tenant_id, key)
        cached_envelope = self._backing_store.get(storage_key)
        if cached_envelope is None:
            return None
        return self.engine.decrypt_str(cached_envelope)

    async def set_secret(self, key: str, value: str, tenant_id: str | None = None) -> None:
        """Encrypt value using envelope encryption and store in database."""
        envelope = self.engine.encrypt(value)

        if self.db_pool is not None:
            query = (
                f"INSERT INTO {self.table_name} (key, tenant_id, key_id, encrypted_dek, "  # noqa: S608
                f"dek_nonce, ciphertext, nonce, algorithm, updated_at) "
                f"VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW()) "
                f"ON CONFLICT (key, tenant_id) DO UPDATE SET "
                f"key_id = EXCLUDED.key_id, encrypted_dek = EXCLUDED.encrypted_dek, "
                f"dek_nonce = EXCLUDED.dek_nonce, ciphertext = EXCLUDED.ciphertext, "
                f"nonce = EXCLUDED.nonce, algorithm = EXCLUDED.algorithm, updated_at = NOW()"
            )
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    key,
                    tenant_id,
                    envelope.key_id,
                    envelope.encrypted_dek,
                    envelope.dek_nonce,
                    envelope.ciphertext,
                    envelope.nonce,
                    envelope.algorithm,
                )
            return

        storage_key = (tenant_id, key)
        self._backing_store[storage_key] = envelope

    async def delete_secret(self, key: str, tenant_id: str | None = None) -> bool:
        """Delete secret from database."""
        if self.db_pool is not None:
            query = (
                f"DELETE FROM {self.table_name} "  # noqa: S608
                f"WHERE key = $1 AND (tenant_id = $2 OR ($2 IS NULL AND tenant_id IS NULL))"
            )
            async with self.db_pool.acquire() as conn:
                result = await conn.execute(query, key, tenant_id)
                return "DELETE 1" in result

        storage_key = (tenant_id, key)
        return self._backing_store.pop(storage_key, None) is not None

    async def rotate_all_secrets(self, tenant_id: str | None = None) -> int:
        """Rotate all secrets to the active KEK by rewrapping DEKs in place.

        Returns the number of secrets rotated.
        """
        rotated_count = 0
        if self.db_pool is not None:
            select_query = (
                f"SELECT key, tenant_id, key_id, encrypted_dek, dek_nonce, "  # noqa: S608
                f"ciphertext, nonce, algorithm FROM {self.table_name} WHERE key_id != $1"
            )
            update_query = (
                f"UPDATE {self.table_name} SET key_id = $1, encrypted_dek = $2, "  # noqa: S608
                f"dek_nonce = $3, updated_at = NOW() WHERE key = $4 AND tenant_id = $5"
            )
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(select_query, self.engine.active_key_id)
                for row in rows:
                    old_envelope = EnvelopeCiphertext(
                        key_id=row["key_id"],
                        encrypted_dek=row["encrypted_dek"],
                        dek_nonce=row["dek_nonce"],
                        ciphertext=row["ciphertext"],
                        nonce=row["nonce"],
                        algorithm=row.get("algorithm", "AES-256-GCM"),
                    )
                    new_envelope = self.engine.rewrap_dek(old_envelope)
                    await conn.execute(
                        update_query,
                        new_envelope.key_id,
                        new_envelope.encrypted_dek,
                        new_envelope.dek_nonce,
                        row["key"],
                        row["tenant_id"],
                    )
                    rotated_count += 1
            return rotated_count

        for storage_key, envelope in list(self._backing_store.items()):
            if tenant_id is not None and storage_key[0] != tenant_id:
                continue
            if envelope.key_id != self.engine.active_key_id:
                new_envelope = self.engine.rewrap_dek(envelope)
                self._backing_store[storage_key] = new_envelope
                rotated_count += 1

        logger.info(
            "Rotated %d secrets to active key '%s'",
            rotated_count,
            self.engine.active_key_id,
        )
        return rotated_count
