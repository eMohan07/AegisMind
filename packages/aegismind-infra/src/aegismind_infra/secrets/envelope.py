from __future__ import annotations

import base64
import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from aegismind_infra.ports import EnvelopeCiphertext

logger = logging.getLogger(__name__)

__all__ = [
    "EnvelopeCiphertext",
    "EnvelopeEncryptionEngine",
    "EnvelopeIntegrityError",
]


class EnvelopeIntegrityError(Exception):
    """Raised when envelope ciphertext authentication or integrity check fails."""


class EnvelopeEncryptionEngine:
    """Envelope encryption engine using AES-256-GCM with per-secret DEKs."""

    def __init__(
        self,
        master_keys: dict[str, bytes] | None = None,
        active_key_id: str = "primary",
    ) -> None:
        """Initialize engine with master Key Encryption Keys (KEKs).

        Args:
            master_keys: Dictionary mapping key IDs to 32-byte master keys.
            active_key_id: The key ID to use for new encryptions.
        """
        self._master_keys: dict[str, bytes] = {}
        if master_keys:
            for kid, key in master_keys.items():
                self.add_key(kid, key)
        else:
            # Generate default primary key if none provided
            self.add_key(active_key_id, os.urandom(32))

        if active_key_id not in self._master_keys:
            msg = f"Active key ID '{active_key_id}' must be present in master keys"
            raise ValueError(msg)
        self._active_key_id = active_key_id

    @property
    def active_key_id(self) -> str:
        """Return the current active key ID used for encryptions."""
        return self._active_key_id

    def add_key(self, key_id: str, key: bytes) -> None:
        """Register a 32-byte (256-bit) master key."""
        if len(key) != 32:
            msg = f"Key '{key_id}' must be exactly 32 bytes (256 bits), got {len(key)} bytes"
            raise ValueError(msg)
        self._master_keys[key_id] = key

    def rotate_key(self, new_key_id: str, new_key: bytes | None = None) -> None:
        """Rotate the active encryption key to a new key ID.

        Existing keys are retained so previous ciphertexts remain decryptable.
        """
        if new_key is None:
            new_key = os.urandom(32)
        self.add_key(new_key_id, new_key)
        self._active_key_id = new_key_id
        logger.info("Rotated active master key to '%s'", new_key_id)

    def encrypt(
        self,
        plaintext: str | bytes,
        associated_data: bytes | None = None,
    ) -> EnvelopeCiphertext:
        """Encrypt plaintext using envelope encryption with per-record DEK.

        1. Generates a fresh 32-byte DEK.
        2. Encrypts plaintext with DEK via AES-GCM.
        3. Encrypts DEK with active KEK via AES-GCM.
        4. Packages encrypted DEK and ciphertext into EnvelopeCiphertext.
        """
        raw_bytes = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext

        # 1. Generate fresh DEK
        dek = os.urandom(32)

        # 2. Encrypt plaintext payload with DEK
        payload_nonce = os.urandom(12)
        payload_aesgcm = AESGCM(dek)
        payload_ciphertext = payload_aesgcm.encrypt(payload_nonce, raw_bytes, associated_data)

        # 3. Encrypt DEK with active KEK
        kek = self._master_keys[self._active_key_id]
        dek_nonce = os.urandom(12)
        kek_aesgcm = AESGCM(kek)
        encrypted_dek = kek_aesgcm.encrypt(
            dek_nonce,
            dek,
            self._active_key_id.encode("utf-8"),
        )

        return EnvelopeCiphertext(
            key_id=self._active_key_id,
            encrypted_dek=base64.b64encode(encrypted_dek).decode("ascii"),
            dek_nonce=base64.b64encode(dek_nonce).decode("ascii"),
            ciphertext=base64.b64encode(payload_ciphertext).decode("ascii"),
            nonce=base64.b64encode(payload_nonce).decode("ascii"),
            algorithm="AES-256-GCM",
        )

    def decrypt(
        self,
        envelope: EnvelopeCiphertext,
        associated_data: bytes | None = None,
    ) -> bytes:
        """Decrypt an envelope ciphertext using the appropriate KEK.

        Raises:
            EnvelopeIntegrityError: If ciphertext, nonces, or DEK has been tampered with.
            KeyError: If key_id is not found in master keys.
        """
        if envelope.key_id not in self._master_keys:
            msg = f"Master key ID '{envelope.key_id}' not found in key provider"
            raise KeyError(msg)

        kek = self._master_keys[envelope.key_id]

        try:
            encrypted_dek = base64.b64decode(envelope.encrypted_dek)
            dek_nonce = base64.b64decode(envelope.dek_nonce)
            ciphertext = base64.b64decode(envelope.ciphertext)
            payload_nonce = base64.b64decode(envelope.nonce)
        except Exception as exc:
            msg = f"Failed to base64 decode envelope fields: {exc}"
            raise EnvelopeIntegrityError(msg) from exc

        # 1. Decrypt DEK with KEK
        kek_aesgcm = AESGCM(kek)
        try:
            dek = kek_aesgcm.decrypt(
                dek_nonce,
                encrypted_dek,
                envelope.key_id.encode("utf-8"),
            )
        except InvalidTag as exc:
            msg = "DEK authentication tag verification failed (ciphertext corrupted or tampered)"
            raise EnvelopeIntegrityError(msg) from exc

        # 2. Decrypt payload with DEK
        payload_aesgcm = AESGCM(dek)
        try:
            plaintext = payload_aesgcm.decrypt(
                payload_nonce,
                ciphertext,
                associated_data,
            )
        except InvalidTag as exc:
            msg = "Payload auth tag verification failed (ciphertext corrupted or tampered)"
            raise EnvelopeIntegrityError(msg) from exc

        return plaintext

    def decrypt_str(
        self,
        envelope: EnvelopeCiphertext,
        associated_data: bytes | None = None,
    ) -> str:
        """Decrypt envelope ciphertext and decode to UTF-8 string."""
        return self.decrypt(envelope, associated_data).decode("utf-8")

    def rewrap_dek(
        self,
        envelope: EnvelopeCiphertext,
    ) -> EnvelopeCiphertext:
        """Re-wrap the DEK with the current active KEK without touching the payload.

        Enables fast key rotation across millions of records without payload re-encryption.
        """
        if envelope.key_id not in self._master_keys:
            msg = f"Master key ID '{envelope.key_id}' not found in key provider"
            raise KeyError(msg)

        old_kek = self._master_keys[envelope.key_id]

        try:
            encrypted_dek = base64.b64decode(envelope.encrypted_dek)
            dek_nonce = base64.b64decode(envelope.dek_nonce)
        except Exception as exc:
            msg = f"Invalid base64 payload in envelope: {exc}"
            raise EnvelopeIntegrityError(msg) from exc

        kek_aesgcm = AESGCM(old_kek)
        try:
            dek = kek_aesgcm.decrypt(
                dek_nonce,
                encrypted_dek,
                envelope.key_id.encode("utf-8"),
            )
        except InvalidTag as exc:
            msg = "DEK verification failed during rewrap"
            raise EnvelopeIntegrityError(msg) from exc

        # Encrypt DEK with new active KEK
        new_kek = self._master_keys[self._active_key_id]
        new_dek_nonce = os.urandom(12)
        new_kek_aesgcm = AESGCM(new_kek)
        new_encrypted_dek = new_kek_aesgcm.encrypt(
            new_dek_nonce,
            dek,
            self._active_key_id.encode("utf-8"),
        )

        return EnvelopeCiphertext(
            key_id=self._active_key_id,
            encrypted_dek=base64.b64encode(new_encrypted_dek).decode("ascii"),
            dek_nonce=base64.b64encode(new_dek_nonce).decode("ascii"),
            ciphertext=envelope.ciphertext,
            nonce=envelope.nonce,
            algorithm=envelope.algorithm,
        )
