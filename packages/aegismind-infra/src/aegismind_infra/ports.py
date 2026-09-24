from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class EnvelopeCiphertext(BaseModel):
    """Encrypted envelope structure containing wrapped DEK and encrypted ciphertext."""

    model_config = ConfigDict(frozen=True)

    key_id: str = Field(..., description="Key identifier of the KEK used to wrap the DEK")
    encrypted_dek: str = Field(..., description="Base64-encoded encrypted Data Encryption Key")
    dek_nonce: str = Field(..., description="Base64-encoded nonce used to encrypt the DEK")
    ciphertext: str = Field(..., description="Base64-encoded ciphertext payload")
    nonce: str = Field(..., description="Base64-encoded nonce used to encrypt payload")
    algorithm: str = Field(default="AES-256-GCM", description="AEAD cipher algorithm")


class StoredObject(BaseModel):
    """Metadata and content container for an object in storage."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(..., description="Object identifier / path")
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME content type of object",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="User-defined metadata key-value pairs",
    )
    tenant_id: str | None = Field(default=None, description="Optional tenant boundary")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when object was stored",
    )


@runtime_checkable
class SecretStorePort(Protocol):
    """Port interface for storing and retrieving secrets with tenant scoping."""

    async def get_secret(self, key: str, tenant_id: str | None = None) -> str | None:
        """Retrieve plaintext secret by key and optional tenant ID."""
        ...

    async def set_secret(self, key: str, value: str, tenant_id: str | None = None) -> None:
        """Store secret under key and optional tenant ID."""
        ...

    async def delete_secret(self, key: str, tenant_id: str | None = None) -> bool:
        """Delete secret by key and optional tenant ID. Returns True if deleted."""
        ...


@runtime_checkable
class ObjectStorePort(Protocol):
    """Port interface for blob and document object storage."""

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """Store object payload and return its URI or key identifier."""
        ...

    async def get_object(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bytes | None:
        """Retrieve object bytes by key."""
        ...

    async def delete_object(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Delete object by key. Returns True if deleted, False if not found."""
        ...

    async def exists(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Check if an object exists."""
        ...

    async def list_objects(
        self,
        prefix: str = "",
        tenant_id: str | None = None,
    ) -> list[str]:
        """List keys matching prefix within optional tenant boundary."""
        ...
