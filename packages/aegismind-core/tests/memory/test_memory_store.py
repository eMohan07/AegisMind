from __future__ import annotations

import json
import sqlite3
import time

import pytest

from aegismind_core.memory.audit import AuditLog, _compute_hash
from aegismind_core.memory.models import (
    MemoryFilter,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
)
from aegismind_core.memory.secret_guard import scan_content
from aegismind_core.memory.settings import MemorySettings
from aegismind_core.memory.sqlite_store import SQLiteMemoryStore, _content_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: pytest.TempPathFactory) -> SQLiteMemoryStore:
    """Autouse-safe: every test gets its own isolated SQLite file."""
    db_file = str(tmp_path / "test_memory.db")
    return SQLiteMemoryStore(db_path=db_file)


@pytest.fixture()
def record() -> MemoryRecord:
    return MemoryRecord(
        namespace="global",
        type=MemoryType.SEMANTIC,
        content="The sky is blue.",
        confidence=0.9,
        importance=0.6,
    )


# ---------------------------------------------------------------------------
# 1. CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_get(store: SQLiteMemoryStore, record: MemoryRecord) -> None:
    saved = await store.add(record)
    assert saved.id
    assert saved.content_hash == _content_hash("The sky is blue.")

    fetched = await store.get(saved.id)
    assert fetched is not None
    assert fetched.content == "The sky is blue."
    assert fetched.status == MemoryStatus.PENDING


@pytest.mark.asyncio
async def test_update(store: SQLiteMemoryStore, record: MemoryRecord) -> None:
    saved = await store.add(record)
    updated = await store.update(saved.id, importance=0.9, status=MemoryStatus.ACTIVE)
    assert updated.importance == pytest.approx(0.9)
    assert updated.status == MemoryStatus.ACTIVE


@pytest.mark.asyncio
async def test_pin(store: SQLiteMemoryStore, record: MemoryRecord) -> None:
    saved = await store.add(record)
    await store.pin(saved.id, True)
    fetched = await store.get(saved.id)
    assert fetched is not None
    assert fetched.pinned is True

    await store.pin(saved.id, False)
    fetched2 = await store.get(saved.id)
    assert fetched2 is not None
    assert fetched2.pinned is False


@pytest.mark.asyncio
async def test_approve_and_reject(store: SQLiteMemoryStore, record: MemoryRecord) -> None:
    saved = await store.add(record)
    approved = await store.approve(saved.id, actor="user")
    assert approved.status == MemoryStatus.ACTIVE

    record2 = MemoryRecord(content="Water is wet.", namespace="global")
    saved2 = await store.add(record2)
    rejected = await store.reject(saved2.id, actor="user")
    assert rejected.status == MemoryStatus.ARCHIVED


@pytest.mark.asyncio
async def test_list_with_filters(store: SQLiteMemoryStore) -> None:
    r1 = MemoryRecord(content="Fact A.", namespace="global", type=MemoryType.EPISODIC)
    r2 = MemoryRecord(content="Fact B.", namespace="global", type=MemoryType.SEMANTIC)
    saved1 = await store.add(r1)
    saved2 = await store.add(r2)
    await store.approve(saved1.id)
    await store.approve(saved2.id)

    episodic = await store.list(MemoryFilter(types=[MemoryType.EPISODIC]))
    assert any(m.id == saved1.id for m in episodic)
    assert all(m.type == MemoryType.EPISODIC for m in episodic)


@pytest.mark.asyncio
async def test_namespace_crud(store: SQLiteMemoryStore) -> None:
    ns = await store.add_namespace("workspace")
    assert ns.name == "workspace"

    fetched = await store.get_namespace("workspace")
    assert fetched is not None
    assert fetched.name == "workspace"

    all_ns = await store.list_namespaces()
    names = [n.name for n in all_ns]
    assert "global" in names
    assert "workspace" in names

    await store.delete_namespace("workspace")
    gone = await store.get_namespace("workspace")
    assert gone is None


@pytest.mark.asyncio
async def test_delete_namespace_with_active_memory_fails(store: SQLiteMemoryStore) -> None:
    await store.add_namespace("ns_protected")
    record = MemoryRecord(content="Important.", namespace="ns_protected")
    saved = await store.add(record)
    await store.approve(saved.id)

    with pytest.raises(ValueError, match="active memories"):
        await store.delete_namespace("ns_protected")


# ---------------------------------------------------------------------------
# 2. Hybrid ranking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_active_only(store: SQLiteMemoryStore) -> None:
    r1 = MemoryRecord(content="Python is a programming language.", namespace="global")
    r2 = MemoryRecord(content="The capital of France is Paris.", namespace="global")
    s1 = await store.add(r1)
    s2 = await store.add(r2)
    await store.approve(s1.id)
    # r2 stays pending

    results = await store.search("Python programming", None, "global", top_k=5)
    ids = [r.memory.id for r in results]
    # Verify approved memory appears and pending does not
    approved_in = s1.id in ids
    pending_in = s2.id in ids
    assert approved_in, f"Approved memory {s1.id} not found in {ids}"
    assert not pending_in, "Pending memory must not appear in active search"


@pytest.mark.asyncio
async def test_pinned_memory_gets_boost(store: SQLiteMemoryStore) -> None:
    r1 = MemoryRecord(content="SQLite is a file-based database.", namespace="global", importance=0.5)
    r2 = MemoryRecord(content="SQLite is embedded in Python.", namespace="global", importance=0.5)
    s1 = await store.add(r1)
    s2 = await store.add(r2)
    await store.approve(s1.id)
    await store.approve(s2.id)
    await store.pin(s2.id, True)

    results = await store.search("SQLite", None, "global", top_k=5)
    assert results, "Expected search results"
    # s2 should score higher because of pin boost
    pinned_result = next((r for r in results if r.memory.id == s2.id), None)
    unpinned_result = next((r for r in results if r.memory.id == s1.id), None)
    assert pinned_result is not None
    assert unpinned_result is not None
    assert pinned_result.score >= unpinned_result.score


@pytest.mark.asyncio
async def test_vector_search_with_embedding(store: SQLiteMemoryStore) -> None:
    # Store two memories with synthetic embeddings; the first is closer to the query
    r1 = MemoryRecord(content="Machine learning models.", namespace="global")
    r2 = MemoryRecord(content="Ancient Roman history.", namespace="global")
    emb_ml = [1.0, 0.0, 0.0, 0.0]
    emb_rome = [0.0, 1.0, 0.0, 0.0]
    query_emb = [0.99, 0.01, 0.0, 0.0]  # closer to emb_ml

    s1 = await store.add(r1, embedding=emb_ml)
    s2 = await store.add(r2, embedding=emb_rome)
    await store.approve(s1.id)
    await store.approve(s2.id)

    results = await store.search("", query_emb, "global", top_k=2)
    assert results[0].memory.id == s1.id


# ---------------------------------------------------------------------------
# 3. Supersede keeps history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supersede_keeps_history(store: SQLiteMemoryStore) -> None:
    old = MemoryRecord(content="We use PostgreSQL.", namespace="global")
    saved_old = await store.add(old)
    await store.approve(saved_old.id)

    new = MemoryRecord(content="We switched to SQLite.", namespace="global")
    updated_old, inserted_new = await store.supersede(saved_old.id, new, actor="user")

    assert updated_old.status == MemoryStatus.SUPERSEDED
    assert updated_old.valid_to is not None
    assert updated_old.superseded_by == inserted_new.id

    # Old record still retrievable
    fetched_old = await store.get(saved_old.id)
    assert fetched_old is not None
    assert fetched_old.status == MemoryStatus.SUPERSEDED

    # History chain
    history = await store.get_history(saved_old.id)
    assert len(history) >= 1


@pytest.mark.asyncio
async def test_superseded_not_in_active_search(store: SQLiteMemoryStore) -> None:
    old = MemoryRecord(content="Old fact about databases.", namespace="global")
    saved = await store.add(old)
    await store.approve(saved.id)

    new = MemoryRecord(content="New fact about databases.", namespace="global")
    updated_old, _ = await store.supersede(saved.id, new, actor="user")

    results = await store.search("databases", None, "global", top_k=5)
    ids = [r.memory.id for r in results]
    assert saved.id not in ids, "Superseded memory must not appear in active search"


# ---------------------------------------------------------------------------
# 4. Tombstone and purge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forget_sets_tombstone(store: SQLiteMemoryStore, record: MemoryRecord) -> None:
    saved = await store.add(record)
    await store.approve(saved.id)
    await store.forget(saved.id, actor="user")

    fetched = await store.get(saved.id)
    assert fetched is not None
    assert fetched.status == MemoryStatus.FORGOTTEN


@pytest.mark.asyncio
async def test_purge_forgotten_removes_old_records(tmp_path: pytest.TempPathFactory) -> None:
    db_file = str(tmp_path / "purge_test.db")
    # purge_after_days minimum is 1; we backdate far beyond that
    settings = MemorySettings(purge_after_days=1)
    store = SQLiteMemoryStore(db_path=db_file, settings=settings)

    record = MemoryRecord(content="To be purged.", namespace="global")
    saved = await store.add(record)
    await store.approve(saved.id)
    await store.forget(saved.id)

    # Backdate updated_at to well before the purge window
    conn = sqlite3.connect(db_file)
    conn.execute(
        "UPDATE memories SET updated_at='2020-01-01T00:00:00+00:00' WHERE id=?",
        (saved.id,),
    )
    conn.commit()
    conn.close()

    count = await store.purge_forgotten()
    assert count >= 1, f"Expected at least 1 purged, got {count}"

    fetched = await store.get(saved.id)
    assert fetched is None, "Purged memory must not be retrievable"




# ---------------------------------------------------------------------------
# 5. Secret guard
# ---------------------------------------------------------------------------


def test_secret_guard_api_key() -> None:
    content = 'api_key = "exampledummyapikey1234567890"'
    is_safe, sanitised, pattern = scan_content(content)
    assert is_safe is False
    assert pattern == "api_key_assignment"
    assert "[REDACTED]" in sanitised
    assert "exampledummyapikey1234567890" not in sanitised


def test_secret_guard_private_key_header() -> None:
    content = "Some text\n-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK..."
    is_safe, sanitised, pattern = scan_content(content)
    assert is_safe is False
    assert pattern == "private_key_header"


def test_secret_guard_password() -> None:
    content = "password = supersecret123"
    is_safe, sanitised, pattern = scan_content(content)
    assert is_safe is False
    assert pattern == "password_assignment"


def test_secret_guard_clean_content() -> None:
    content = "The sky is blue and grass is green."
    is_safe, sanitised, pattern = scan_content(content)
    assert is_safe is True
    assert pattern is None
    assert sanitised == content


@pytest.mark.asyncio
@pytest.mark.guardrail
async def test_secret_guard_blocks_add(store: SQLiteMemoryStore) -> None:
    record = MemoryRecord(
        content='OPENAI_API_KEY = "sk-verylongkey1234567890abcdef"',
        namespace="global",
    )
    with pytest.raises(ValueError, match="secret guard"):
        await store.add(record)


@pytest.mark.asyncio
@pytest.mark.guardrail
async def test_secret_guard_private_key_blocked(store: SQLiteMemoryStore) -> None:
    record = MemoryRecord(
        content="key: -----BEGIN PRIVATE KEY-----\nMIIE...",
        namespace="global",
    )
    with pytest.raises(ValueError, match="secret guard"):
        await store.add(record)


# ---------------------------------------------------------------------------
# 6. Hash chain verifies and detects tampering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hash_chain_verifies(store: SQLiteMemoryStore) -> None:
    r1 = MemoryRecord(content="Event one.", namespace="global")
    r2 = MemoryRecord(content="Event two.", namespace="global")
    s1 = await store.add(r1)
    s2 = await store.add(r2)
    await store.approve(s1.id)
    await store.forget(s2.id)

    ok, err = await store.verify_audit()
    assert ok is True, f"Audit chain should be valid but got: {err}"


@pytest.mark.asyncio
@pytest.mark.guardrail
async def test_hash_chain_detects_tampering(store: SQLiteMemoryStore) -> None:
    r = MemoryRecord(content="Tamper me.", namespace="global")
    saved = await store.add(r)
    await store.approve(saved.id)

    # Directly tamper with audit log row (simulates attacker editing the DB)
    conn = sqlite3.connect(store.db_path)
    # Temporarily disable the append-only triggers so we can modify
    conn.execute("DROP TRIGGER IF EXISTS memory_events_no_update")
    conn.execute(
        "UPDATE memory_events SET payload='{\"tampered\": true}' WHERE seq=1"
    )
    conn.commit()
    conn.close()

    ok, err = store.audit.verify()
    assert ok is False, "Tampered chain should fail verification"
    assert "seq=1" in err or "mismatch" in err.lower()


@pytest.mark.asyncio
@pytest.mark.guardrail
async def test_append_only_triggers_block_update(store: SQLiteMemoryStore) -> None:
    """DB-level triggers must prevent direct UPDATE on memory_events."""
    r = MemoryRecord(content="Immutable audit entry.", namespace="global")
    await store.add(r)

    conn = sqlite3.connect(store.db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE memory_events SET actor='hacker' WHERE seq=1")
        conn.commit()
    conn.close()


@pytest.mark.asyncio
@pytest.mark.guardrail
async def test_append_only_triggers_block_delete(store: SQLiteMemoryStore) -> None:
    """DB-level triggers must prevent direct DELETE on memory_events."""
    r = MemoryRecord(content="Delete me if you can.", namespace="global")
    await store.add(r)

    conn = sqlite3.connect(store.db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM memory_events WHERE seq=1")
        conn.commit()
    conn.close()



# ---------------------------------------------------------------------------
# 7. Export / import / backup / restore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_and_import_roundtrip(
    store: SQLiteMemoryStore, tmp_path: pytest.TempPathFactory
) -> None:
    r = MemoryRecord(content="Exportable fact.", namespace="global")
    saved = await store.add(r)
    await store.approve(saved.id)

    exported = await store.export_all()
    assert len(exported["memories"]) >= 1

    # Import into a fresh store
    db2 = str(tmp_path / "import_test.db")
    store2 = SQLiteMemoryStore(db_path=db2)
    count = await store2.import_all(exported)
    assert count >= 1

    # Re-import the same data should skip duplicates
    count2 = await store2.import_all(exported)
    assert count2 == 0


@pytest.mark.asyncio
async def test_backup_and_restore(
    tmp_path: pytest.TempPathFactory,
) -> None:
    db_path = str(tmp_path / "primary.db")
    backup_path = str(tmp_path / "backup.db")

    store = SQLiteMemoryStore(db_path=db_path)
    r = MemoryRecord(content="Backed up fact.", namespace="global")
    saved = await store.add(r)
    await store.approve(saved.id)

    # Backup while memory is active
    await store.backup(backup_path)

    # Forget the memory (simulate data loss / bad operation)
    await store.forget(saved.id)
    mid_check = await store.get(saved.id)
    assert mid_check is not None
    assert mid_check.status == MemoryStatus.FORGOTTEN

    # Restore: uses sqlite3 native backup() API so in-process connections are updated
    await store.restore(backup_path)

    # Open a fresh connection to the same db_path to read the restored state
    fresh_store = SQLiteMemoryStore(db_path=db_path)
    fetched = await fresh_store.get(saved.id)
    assert fetched is not None, "Memory must survive backup/restore roundtrip"
    assert fetched.status == MemoryStatus.ACTIVE




# ---------------------------------------------------------------------------
# 8. Touch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_touch_increments_access_count(
    store: SQLiteMemoryStore, record: MemoryRecord
) -> None:
    saved = await store.add(record)
    assert saved.access_count == 0

    await store.touch([saved.id])
    fetched = await store.get(saved.id)
    assert fetched is not None
    assert fetched.access_count == 1
    assert fetched.last_accessed_at is not None


# ---------------------------------------------------------------------------
# 9. Stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats(store: SQLiteMemoryStore) -> None:
    r = MemoryRecord(content="Stats test.", namespace="global")
    saved = await store.add(r)
    await store.approve(saved.id)

    stats = store.get_stats()
    assert stats["total"] >= 1
    assert stats["by_status"].get("active", 0) >= 1
