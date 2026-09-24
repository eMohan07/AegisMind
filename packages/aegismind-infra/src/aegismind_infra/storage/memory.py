from __future__ import annotations

import logging
from datetime import UTC, datetime

from aegismind_infra.ports import ObjectStorePort, StoredObject

logger = logging.getLogger(__name__)


class MemoryObjectStore(ObjectStorePort):
    """In-memory object store for isolated development and tests."""

    def __init__(self) -> None:
        self._objects: dict[str, StoredObject] = {}
        self._data: dict[str, bytes] = {}

    def _resolve_key(self, key: str, tenant_id: str | None) -> str:
        clean_key = key.lstrip("/")
        if tenant_id:
            return f"{tenant_id}/{clean_key}"
        return clean_key

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """Store an object in memory."""
        full_key = self._resolve_key(key, tenant_id)
        self._data[full_key] = data
        self._objects[full_key] = StoredObject(
            key=key,
            content_type=content_type,
            metadata=metadata or {},
            tenant_id=tenant_id,
            created_at=datetime.now(UTC),
        )
        logger.debug("Stored in-memory object '%s' (%d bytes)", full_key, len(data))
        return f"memory://{full_key}"

    async def get_object(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bytes | None:
        """Retrieve object bytes by key."""
        full_key = self._resolve_key(key, tenant_id)
        return self._data.get(full_key)

    async def delete_object(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Delete an object from memory."""
        full_key = self._resolve_key(key, tenant_id)
        self._objects.pop(full_key, None)
        return self._data.pop(full_key, None) is not None

    async def exists(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Check whether object exists in memory."""
        full_key = self._resolve_key(key, tenant_id)
        return full_key in self._data

    async def list_objects(
        self,
        prefix: str = "",
        tenant_id: str | None = None,
    ) -> list[str]:
        """List object keys matching prefix within tenant boundary."""
        prefix_key = self._resolve_key(prefix, tenant_id)
        matched_keys: list[str] = []
        for full_key, meta in self._objects.items():
            if tenant_id and meta.tenant_id != tenant_id:
                continue
            if full_key.startswith(prefix_key):
                matched_keys.append(meta.key)
        return sorted(matched_keys)
