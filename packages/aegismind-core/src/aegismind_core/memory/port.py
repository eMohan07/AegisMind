from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aegismind_core.memory.models import (
    MemoryEvent,
    MemoryFilter,
    MemoryRecord,
    MemoryType,
    Namespace,
    ScoredMemory,
)


@runtime_checkable
class MemoryStorePort(Protocol):
    """Port (interface) for the long-term memory store.

    Implementations must be backed by a persistent store.  The SQLite adapter
    is the production implementation; a lightweight in-memory stub can be used
    in tests that do not need persistence.

    All public methods are async so callers in FastAPI route handlers and the
    agent loop can await them without blocking the event loop.  Implementations
    are expected to run their blocking I/O via asyncio.to_thread().
    """

    # ------------------------------------------------------------------
    # Namespace management
    # ------------------------------------------------------------------

    async def add_namespace(self, name: str) -> Namespace:
        """Create a new namespace. No-op if already exists; returns existing."""
        ...

    async def get_namespace(self, name: str) -> Namespace | None:
        """Return Namespace by name, or None if not found."""
        ...

    async def list_namespaces(self) -> list[Namespace]:
        """Return all namespaces ordered by created_at."""
        ...

    async def delete_namespace(self, name: str) -> None:
        """Remove a namespace. Refuses if any active memories belong to it."""
        ...

    # ------------------------------------------------------------------
    # Memory CRUD
    # ------------------------------------------------------------------

    async def add(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a new memory and return the stored record (with content_hash set)."""
        ...

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Return a memory by primary key, or None."""
        ...

    async def update(self, memory_id: str, **fields: Any) -> MemoryRecord:
        """Partial-update a memory.  Raises KeyError if not found."""
        ...

    async def pin(self, memory_id: str, pinned: bool) -> None:
        """Toggle the pinned flag without touching the updated_at timestamp."""
        ...

    async def approve(self, memory_id: str, actor: str = "user") -> MemoryRecord:
        """Move a pending memory to active status."""
        ...

    async def reject(self, memory_id: str, actor: str = "user") -> MemoryRecord:
        """Move a pending memory to archived status (rejected, kept for history)."""
        ...

    # ------------------------------------------------------------------
    # Supersede
    # ------------------------------------------------------------------

    async def supersede(
        self,
        old_id: str,
        new_memory: MemoryRecord,
        actor: str = "system",
    ) -> tuple[MemoryRecord, MemoryRecord]:
        """Mark *old_id* as superseded and insert *new_memory*.

        Returns (updated_old, inserted_new).
        The old record gets: status=superseded, valid_to=now, superseded_by=new.id.
        The new record starts with status=pending (goes through approval flow).
        """
        ...

    # ------------------------------------------------------------------
    # Forgetting
    # ------------------------------------------------------------------

    async def forget(
        self,
        memory_id: str,
        actor: str = "user",
    ) -> None:
        """Soft-delete: set status=forgotten (tombstone).
        Hard-purged automatically after purge_after_days by purge_forgotten().
        """
        ...

    async def purge_forgotten(self) -> int:
        """Hard-delete memories in forgotten status older than purge_after_days.
        Returns count of rows permanently deleted.
        """
        ...

    # ------------------------------------------------------------------
    # Listing and search
    # ------------------------------------------------------------------

    async def list(self, filters: MemoryFilter) -> list[MemoryRecord]:
        """List memories matching the given filter criteria."""
        ...

    async def search(
        self,
        query: str,
        embedding: list[float] | None,
        namespace: str,
        types: list[MemoryType] | None = None,
        top_k: int = 5,
        include_global: bool = True,
    ) -> list[ScoredMemory]:
        """Hybrid (FTS5 + cosine) search with RRF fusion and composite scoring."""
        ...

    async def touch(self, ids: list[str]) -> None:
        """Update last_accessed_at and increment access_count for each id."""
        ...

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    async def list_audit(
        self,
        limit: int = 100,
        offset: int = 0,
        memory_id: str | None = None,
    ) -> list[MemoryEvent]:
        """Return audit events newest-first."""
        ...

    async def verify_audit(self) -> tuple[bool, str]:
        """Verify the hash chain. Returns (ok, error_description)."""
        ...

    # ------------------------------------------------------------------
    # Export / import / backup / restore
    # ------------------------------------------------------------------

    async def export_all(self) -> dict[str, Any]:
        """Export all memories and namespaces as a JSON-serialisable dict."""
        ...

    async def import_all(self, data: dict[str, Any], actor: str = "import") -> int:
        """Import memories from an export dict; skip exact-content duplicates.
        Returns count of newly inserted memories.
        """
        ...

    async def backup(self, path: str) -> None:
        """Create a binary backup of the SQLite database file."""
        ...

    async def restore(self, path: str) -> None:
        """Restore the database from a backup file.  Replaces current content."""
        ...
