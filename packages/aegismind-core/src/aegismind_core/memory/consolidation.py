from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aegismind_core.memory.models import MemoryFilter, MemoryRecord, MemoryStatus, MemoryType
from aegismind_core.memory.settings import DEFAULT_SETTINGS, MemorySettings
from aegismind_core.memory.sqlite_store import SQLiteMemoryStore, _cosine

logger = logging.getLogger(__name__)


class ConsolidationReport(BaseModel):
    """Summary of operations performed during a memory consolidation run."""

    model_config = ConfigDict(frozen=True)

    namespace: str
    purged_forgotten: int = 0
    archived_stale: int = 0
    merged_records: int = 0
    errors: list[str] = Field(default_factory=list)


class MemoryConsolidator:
    """Background consolidation service for long-term memory.

    Performs three maintenance tasks:
    1. Purges forgotten tombstones past retention period.
    2. Archives stale, unpinned, unaccessed episodic memories.
    3. Merges highly similar or duplicate semantic memories into consolidated records.
    """

    def __init__(
        self,
        store: SQLiteMemoryStore,
        settings: MemorySettings | None = None,
        llm_fn: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or DEFAULT_SETTINGS
        self.llm_fn = llm_fn

    async def run(
        self,
        namespace: str = "global",
        purge_tombstones: bool = True,
        archive_stale: bool = True,
        merge_similar: bool = True,
        stale_days: int = 60,
    ) -> ConsolidationReport:
        """Execute a full consolidation cycle for a namespace."""
        purged = 0
        archived = 0
        merged = 0
        errors: list[str] = []

        # 1. Purge forgotten tombstones
        if purge_tombstones:
            try:
                purged = await self.store.purge_forgotten()
                logger.info("Purged %d forgotten memory tombstones", purged)
            except Exception as exc:
                err_msg = f"Purge forgotten failed: {exc}"
                logger.warning(err_msg)
                errors.append(err_msg)

        # 2. Archive stale memories
        if archive_stale:
            try:
                archived = await self._archive_stale_memories(
                    namespace=namespace,
                    older_than_days=stale_days,
                )
                logger.info("Archived %d stale memories in namespace '%s'", archived, namespace)
            except Exception as exc:
                err_msg = f"Archive stale failed: {exc}"
                logger.warning(err_msg)
                errors.append(err_msg)

        # 3. Merge similar memories
        if merge_similar:
            try:
                merged = await self._merge_similar_memories(namespace=namespace)
                logger.info("Merged %d memory pairs in namespace '%s'", merged, namespace)
            except Exception as exc:
                err_msg = f"Merge similar failed: {exc}"
                logger.warning(err_msg)
                errors.append(err_msg)

        return ConsolidationReport(
            namespace=namespace,
            purged_forgotten=purged,
            archived_stale=archived,
            merged_records=merged,
            errors=errors,
        )

    async def _archive_stale_memories(self, namespace: str, older_than_days: int) -> int:
        """Find unpinned episodic memories older than threshold with zero access, and forget them."""
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        filters = MemoryFilter(
            namespace=namespace,
            statuses=[MemoryStatus.ACTIVE],
            types=[MemoryType.EPISODIC],
            pinned=False,
            limit=200,
        )
        candidates = await self.store.list(filters)
        archived_count = 0

        for mem in candidates:
            # Check if created before cutoff and never accessed or rarely accessed
            if mem.created_at < cutoff and mem.access_count == 0:
                await self.store.forget(mem.id, actor="consolidation_job")
                archived_count += 1

        return archived_count

    async def _merge_similar_memories(self, namespace: str) -> int:
        """Find pairs of similar memories and merge them into a single consolidated record."""
        filters = MemoryFilter(
            namespace=namespace,
            statuses=[MemoryStatus.ACTIVE],
            types=[MemoryType.SEMANTIC],
            limit=100,
        )
        memories = await self.store.list(filters)
        if len(memories) < 2:
            return 0

        # Retrieve raw embeddings from store connection for comparison
        embeddings: dict[str, list[float]] = {}
        for m in memories:
            emb = await asyncio.to_thread(self._get_raw_embedding, m.id)
            if emb:
                embeddings[m.id] = emb

        merged_count = 0
        superseded_ids: set[str] = set()

        # Compare pairs
        for i in range(len(memories)):
            m1 = memories[i]
            if m1.id in superseded_ids:
                continue
            emb1 = embeddings.get(m1.id)
            if not emb1:
                continue

            for j in range(i + 1, len(memories)):
                m2 = memories[j]
                if m2.id in superseded_ids:
                    continue
                emb2 = embeddings.get(m2.id)
                if not emb2:
                    continue

                sim = _cosine(emb1, emb2)
                # If high similarity (>= 0.88), merge them
                if sim >= self.settings.dedup_similarity_threshold:
                    success = await self._merge_pair(m1, m2, emb1)
                    if success:
                        superseded_ids.add(m1.id)
                        superseded_ids.add(m2.id)
                        merged_count += 1
                        break

        return merged_count

    def _get_raw_embedding(self, memory_id: str) -> list[float] | None:
        """Extract unpacked embedding float vector from SQLite."""
        import struct

        conn = self.store._conn()
        row = conn.execute("SELECT embedding FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row or not row[0]:
            return None
        blob = row[0]
        n_floats = len(blob) // 4
        return list(struct.unpack(f"{n_floats}f", blob))

    async def _merge_pair(
        self,
        m1: MemoryRecord,
        m2: MemoryRecord,
        new_embedding: list[float],
    ) -> bool:
        """Combine two memories into a synthesized memory and supersede both."""
        combined_entities = sorted(list(set(m1.entities + m2.entities)))
        combined_importance = max(m1.importance, m2.importance)
        combined_confidence = max(m1.confidence, m2.confidence)

        if self.llm_fn:
            prompt = (
                f"Consolidate the following two related facts into one concise, factual statement.\n"
                f"Fact 1: {m1.content}\n"
                f"Fact 2: {m2.content}\n"
                f"Consolidated statement:"
            )
            try:
                synthesized_text = await self.llm_fn(prompt)
                synthesized_text = synthesized_text.strip().strip('"')
            except Exception as exc:
                logger.warning("LLM consolidation synthesis failed: %s; falling back to union", exc)
                synthesized_text = f"{m1.content} {m2.content}"
        else:
            if m1.content.rstrip(".") in m2.content:
                synthesized_text = m2.content
            elif m2.content.rstrip(".") in m1.content:
                synthesized_text = m1.content
            else:
                synthesized_text = f"{m1.content} {m2.content}"

        new_mem = MemoryRecord(
            namespace=m1.namespace,
            type=m1.type,
            content=synthesized_text,
            entities_json=combined_entities,
            confidence=combined_confidence,
            importance=combined_importance,
            status=MemoryStatus.ACTIVE,
            pinned=m1.pinned or m2.pinned,
        )

        try:
            now = datetime.now(UTC).isoformat()
            # Supersede m1 with new_mem
            _, active_record = await self.store.supersede(
                old_id=m1.id,
                new_memory=new_mem,
                actor="consolidation_merge",
                embedding=new_embedding,
            )
            # Mark m2 as superseded first to prevent active content_hash collision
            await self.store.update(
                m2.id,
                status=MemoryStatus.SUPERSEDED,
                valid_to=now,
                superseded_by=active_record.id,
            )
            self.store.audit.append(
                "superseded",
                actor="consolidation_merge",
                memory_id=m2.id,
                payload={"new_memory_id": active_record.id},
            )

            # Approve the merged memory so it becomes active
            await self.store.approve(active_record.id, actor="consolidation_merge")
            return True
        except Exception as exc:
            logger.error("Failed to apply supersede during merge: %s", exc)
            return False
