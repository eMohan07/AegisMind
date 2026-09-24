from __future__ import annotations

import base64
import os

import pytest
from aegismind_infra.secrets.envelope import (
    EnvelopeCiphertext,
    EnvelopeEncryptionEngine,
    EnvelopeIntegrityError,
)
from aegismind_infra.secrets.memory import MemorySecretStore
from aegismind_infra.secrets.postgres_envelope import PostgresEnvelopeSecretStore


def test_envelope_encryption_round_trip() -> None:
    engine = EnvelopeEncryptionEngine(active_key_id="k1")
    plaintext = "super-secret-api-key-value-12345"

    envelope = engine.encrypt(plaintext)
    assert isinstance(envelope, EnvelopeCiphertext)
    assert envelope.key_id == "k1"
    assert envelope.algorithm == "AES-256-GCM"
    assert envelope.ciphertext != plaintext

    decrypted = engine.decrypt_str(envelope)
    assert decrypted == plaintext


def test_envelope_encryption_bytes_round_trip() -> None:
    engine = EnvelopeEncryptionEngine(active_key_id="k1")
    raw_data = b"\x00\x01\x02\x03\x04\xfe\xff"

    envelope = engine.encrypt(raw_data)
    decrypted = engine.decrypt(envelope)
    assert decrypted == raw_data


def test_envelope_key_rotation() -> None:
    k1 = os.urandom(32)
    k2 = os.urandom(32)

    engine = EnvelopeEncryptionEngine(
        master_keys={"k1": k1},
        active_key_id="k1",
    )
    secret_text = "database-password-prod"
    envelope_v1 = engine.encrypt(secret_text)
    assert envelope_v1.key_id == "k1"

    # Rotate active key to k2
    engine.rotate_key("k2", k2)
    assert engine.active_key_id == "k2"

    # v1 envelope should still be decryptable using retained k1
    assert engine.decrypt_str(envelope_v1) == secret_text

    # Re-wrap DEK to active key k2 without re-encrypting payload
    envelope_v2 = engine.rewrap_dek(envelope_v1)
    assert envelope_v2.key_id == "k2"
    assert envelope_v2.ciphertext == envelope_v1.ciphertext
    assert envelope_v2.nonce == envelope_v1.nonce
    assert envelope_v2.encrypted_dek != envelope_v1.encrypted_dek

    # Verify decrypt with k2
    assert engine.decrypt_str(envelope_v2) == secret_text

    # Now create engine with ONLY k2 (simulating retirement of k1)
    engine_retired = EnvelopeEncryptionEngine(
        master_keys={"k2": k2},
        active_key_id="k2",
    )
    assert engine_retired.decrypt_str(envelope_v2) == secret_text

    # Attempting to decrypt envelope_v1 with retired k1 raises KeyError
    with pytest.raises(KeyError):
        engine_retired.decrypt_str(envelope_v1)


def test_envelope_ciphertext_integrity_tamper_payload() -> None:
    engine = EnvelopeEncryptionEngine()
    envelope = engine.encrypt("confidential-document-content")

    # Tamper with the ciphertext bytes
    raw_ct = bytearray(base64.b64decode(envelope.ciphertext))
    raw_ct[0] ^= 0xFF  # Flip bits in first byte
    tampered_ct = base64.b64encode(raw_ct).decode("ascii")

    tampered_envelope = EnvelopeCiphertext(
        key_id=envelope.key_id,
        encrypted_dek=envelope.encrypted_dek,
        dek_nonce=envelope.dek_nonce,
        ciphertext=tampered_ct,
        nonce=envelope.nonce,
        algorithm=envelope.algorithm,
    )

    with pytest.raises(EnvelopeIntegrityError):
        engine.decrypt(tampered_envelope)


def test_envelope_ciphertext_integrity_tamper_dek() -> None:
    engine = EnvelopeEncryptionEngine()
    envelope = engine.encrypt("confidential-document-content")

    # Tamper with encrypted DEK
    raw_dek = bytearray(base64.b64decode(envelope.encrypted_dek))
    raw_dek[5] ^= 0xAA
    tampered_dek = base64.b64encode(raw_dek).decode("ascii")

    tampered_envelope = EnvelopeCiphertext(
        key_id=envelope.key_id,
        encrypted_dek=tampered_dek,
        dek_nonce=envelope.dek_nonce,
        ciphertext=envelope.ciphertext,
        nonce=envelope.nonce,
        algorithm=envelope.algorithm,
    )

    with pytest.raises(EnvelopeIntegrityError):
        engine.decrypt(tampered_envelope)


def test_envelope_ciphertext_integrity_tamper_nonce() -> None:
    engine = EnvelopeEncryptionEngine()
    envelope = engine.encrypt("confidential-document-content")

    # Tamper with payload nonce
    raw_nonce = bytearray(base64.b64decode(envelope.nonce))
    raw_nonce[0] ^= 0x01
    tampered_nonce = base64.b64encode(raw_nonce).decode("ascii")

    tampered_envelope = EnvelopeCiphertext(
        key_id=envelope.key_id,
        encrypted_dek=envelope.encrypted_dek,
        dek_nonce=envelope.dek_nonce,
        ciphertext=envelope.ciphertext,
        nonce=tampered_nonce,
        algorithm=envelope.algorithm,
    )

    with pytest.raises(EnvelopeIntegrityError):
        engine.decrypt(tampered_envelope)


@pytest.mark.asyncio
async def test_postgres_envelope_secret_store_lifecycle() -> None:
    engine = EnvelopeEncryptionEngine(active_key_id="k1")
    store = PostgresEnvelopeSecretStore(engine=engine)

    # Set and get secret
    await store.set_secret("openai_api_key", "sk-live-12345", tenant_id="tenant_alpha")
    val = await store.get_secret("openai_api_key", tenant_id="tenant_alpha")
    assert val == "sk-live-12345"

    # Cross-tenant isolation
    other_val = await store.get_secret("openai_api_key", tenant_id="tenant_beta")
    assert other_val is None

    # Rotate keys in store
    engine.rotate_key("k2")
    rotated = await store.rotate_all_secrets()
    assert rotated == 1

    # Verify secret is still readable after store-wide rotation
    val_after_rotation = await store.get_secret("openai_api_key", tenant_id="tenant_alpha")
    assert val_after_rotation == "sk-live-12345"

    # Delete secret
    deleted = await store.delete_secret("openai_api_key", tenant_id="tenant_alpha")
    assert deleted is True
    assert await store.get_secret("openai_api_key", tenant_id="tenant_alpha") is None


@pytest.mark.asyncio
async def test_memory_secret_store() -> None:
    store = MemorySecretStore()
    await store.set_secret("jwt_secret", "secret-key-xyz")
    assert await store.get_secret("jwt_secret") == "secret-key-xyz"

    raw_env = store.get_envelope("jwt_secret")
    assert raw_env is not None
    assert raw_env.key_id == store.engine.active_key_id

    assert await store.delete_secret("jwt_secret") is True
    assert await store.get_secret("jwt_secret") is None
