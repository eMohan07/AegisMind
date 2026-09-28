from __future__ import annotations

from datetime import UTC, datetime, timedelta
import pytest

from aegismind_core.memory.consolidation import MemoryConsolidator
from aegismind_core.memory.models import MemoryFilter, MemoryRecord, MemoryStatus, MemoryType
from aegismind_core.memory.settings import MemorySettings
from aegismind_core.memory.sqlite_store import SQLiteMemoryStore


@pytest.fixture
def store(tmp_path: pytest.TempPathFactory) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path=str(tmp_path / "consolidation_test.db"))


@pytest.mark.asyncio
async def test_consolidation_purge_forgotten(store: SQLiteMemoryStore) -> None:
    # Add a memory, approve, then forget it
    mem = MemoryRecord(content="To be forgotten", namespace="global")
    saved = await store.add(mem)
    await store.approve(saved.id)
    await store.forget(saved.id)

    # Backdate updated_at so it passes retention window
    old_time = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    conn = store._conn()
    conn.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (old_time, saved.id))
    conn.commit()

    consolidator = MemoryConsolidator(store=store, settings=MemorySettings(purge_after_days=30))
    report = await consolidator.run(namespace="global", purge_tombstones=True, archive_stale=False, merge_similar=False)

    assert report.purged_forgotten == 1
    assert await store.get(saved.id) is None


@pytest.mark.asyncio
async def test_consolidation_archive_stale(store: SQLiteMemoryStore) -> None:
    # Stale episodic memory, unpinned, zero access
    mem = MemoryRecord(
        content="User visited documentation page last month",
        type=MemoryType.EPISODIC,
        namespace="global",
        pinned=False,
    )
    saved = await store.add(mem)
    await store.approve(saved.id)

    # Backdate created_at to 90 days ago
    old_time = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    conn = store._conn()
    conn.execute("UPDATE memories SET created_at = ? WHERE id = ?", (old_time, saved.id))
    conn.commit()

    consolidator = MemoryConsolidator(store=store)
    report = await consolidator.run(
        namespace="global",
        purge_tombstones=False,
        archive_stale=True,
        merge_similar=False,
        stale_days=60,
    )

    assert report.archived_stale == 1
    updated = await store.get(saved.id)
    assert updated is not None
    assert updated.status == MemoryStatus.FORGOTTEN


@pytest.mark.asyncio
async def test_consolidation_merge_similar(store: SQLiteMemoryStore) -> None:
    # Two similar semantic memories with overlapping embeddings
    emb1 = [1.0, 0.0, 0.0, 0.0]
    emb2 = [0.99, 0.01, 0.0, 0.0]

    mem1 = MemoryRecord(
        content="User prefers Python 3.12 for backend services.",
        type=MemoryType.SEMANTIC,
        namespace="global",
    )
    mem2 = MemoryRecord(
        content="User prefers Python 3.12 for backend services and FastAPI.",
        type=MemoryType.SEMANTIC,
        namespace="global",
    )

    s1 = await store.add(mem1, embedding=emb1)
    s2 = await store.add(mem2, embedding=emb2)
    await store.approve(s1.id)
    await store.approve(s2.id)

    consolidator = MemoryConsolidator(
        store=store,
        settings=MemorySettings(dedup_similarity_threshold=0.90),
    )
    report = await consolidator.run(
        namespace="global",
        purge_tombstones=False,
        archive_stale=False,
        merge_similar=True,
    )

    assert report.merged_records == 1
    # Check that original memories are superseded
    m1_refreshed = await store.get(s1.id)
    m2_refreshed = await store.get(s2.id)
    assert m1_refreshed.status == MemoryStatus.SUPERSEDED
    assert m2_refreshed.status == MemoryStatus.SUPERSEDED

    # Active memory list should now have the newly consolidated memory
    active = await store.list(MemoryFilter(namespace="global", statuses=[MemoryStatus.ACTIVE]))
    assert len(active) == 1
    assert "Python 3.12" in active[0].content
