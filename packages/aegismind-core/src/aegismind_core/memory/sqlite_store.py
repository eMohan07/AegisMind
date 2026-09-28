from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import shutil
import sqlite3
import struct
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aegismind_core.memory.audit import AuditLog
from aegismind_core.memory.models import (
    MemoryEvent,
    MemoryFilter,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    Namespace,
    ScoredMemory,
)
from aegismind_core.memory.secret_guard import scan_content
from aegismind_core.memory.settings import DEFAULT_SETTINGS, MemorySettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Migration definitions (append only - never edit existing entries)
# ---------------------------------------------------------------------------

_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS namespaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        INSERT OR IGNORE INTO namespaces (id, name, created_at)
        VALUES ('global-ns', 'global', datetime('now'));

        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            namespace TEXT NOT NULL DEFAULT 'global',
            type TEXT NOT NULL DEFAULT 'semantic',
            content TEXT NOT NULL,
            entities_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL DEFAULT 1.0,
            importance REAL NOT NULL DEFAULT 0.5,
            status TEXT NOT NULL DEFAULT 'pending',
            pinned INTEGER NOT NULL DEFAULT 0,
            sensitivity TEXT NOT NULL DEFAULT 'normal',
            source_thread_id TEXT,
            source_message_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_accessed_at TEXT,
            access_count INTEGER NOT NULL DEFAULT 0,
            valid_from TEXT,
            valid_to TEXT,
            superseded_by TEXT,
            content_hash TEXT NOT NULL DEFAULT '',
            embedding BLOB
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_memory_hash_active
            ON memories(namespace, content_hash)
            WHERE status = 'active';

        CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace);
        CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
        CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
        CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
        CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);

        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content,
            content='memories',
            content_rowid='rowid'
        );

        -- FTS synchronisation triggers
        CREATE TRIGGER IF NOT EXISTS memories_ai
        AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content)
            VALUES (new.rowid, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS memories_ad
        AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS memories_au
        AFTER UPDATE OF content ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
            INSERT INTO memories_fts(rowid, content)
            VALUES (new.rowid, new.content);
        END;

        CREATE TABLE IF NOT EXISTS memory_events (
            seq INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            event TEXT NOT NULL,
            memory_id TEXT,
            actor TEXT NOT NULL DEFAULT 'system',
            payload TEXT NOT NULL DEFAULT '{}',
            prev_hash TEXT NOT NULL,
            hash TEXT NOT NULL
        );

        -- Enforce append-only semantics at the DB level
        CREATE TRIGGER IF NOT EXISTS memory_events_no_update
        BEFORE UPDATE ON memory_events BEGIN
            SELECT RAISE(ABORT, 'memory_events is append-only: UPDATE is forbidden');
        END;

        CREATE TRIGGER IF NOT EXISTS memory_events_no_delete
        BEFORE DELETE ON memory_events BEGIN
            SELECT RAISE(ABORT, 'memory_events is append-only: DELETE is forbidden');
        END;
        """,
    ),
]


# ---------------------------------------------------------------------------
# Embedding helpers (stdlib struct - no third-party deps)
# ---------------------------------------------------------------------------


def _pack_embedding(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


def _unpack_embedding(b: bytes | None) -> list[float] | None:
    if not b:
        return None
    n = len(b) // 4
    return list(struct.unpack(f"{n}f", b))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.strip().lower().encode("utf-8")).hexdigest()


def _recency_decay(last_ts: str | None, created_ts: str, half_life_days: float) -> float:
    """Exponential decay: 2^(-days_elapsed / half_life)."""
    ref = last_ts or created_ts
    try:
        ref_dt = datetime.fromisoformat(ref)
    except ValueError:
        ref_dt = datetime.now(UTC)
    days = (datetime.now(UTC) - ref_dt).total_seconds() / 86400.0
    return math.pow(2.0, -days / half_life_days)


def _sanitise_fts_query(q: str) -> str:
    """Build an FTS5 query that matches any of the individual terms.

    We split the query into tokens, strip punctuation, filter out operator keywords
    ('and', 'or', 'not'), and join with OR.
    """
    import string

    special = set(string.punctuation)
    stop = {"and", "or", "not"}
    tokens = [
        "".join(c for c in tok if c not in special)
        for tok in q.lower().split()
        if tok
    ]
    tokens = [t for t in tokens if t and t not in stop]
    if not tokens:
        return '""'
    return " OR ".join(tokens)


# ---------------------------------------------------------------------------
# Row -> MemoryRecord
# ---------------------------------------------------------------------------


def _row_to_record(row: tuple[Any, ...]) -> MemoryRecord:
    (
        r_id, ns, rtype, content, entities_raw, confidence, importance,
        status, pinned, sensitivity, src_thread, src_msgs_raw,
        created_at, updated_at, last_accessed_at, access_count,
        valid_from, valid_to, superseded_by, content_hash,
        _embedding_blob,
    ) = row
    return MemoryRecord(
        id=r_id,
        namespace=ns,
        type=MemoryType(rtype),
        content=content,
        entities_json=json.loads(entities_raw) if entities_raw else [],
        confidence=float(confidence),
        importance=float(importance),
        status=MemoryStatus(status),
        pinned=bool(pinned),
        sensitivity=sensitivity,
        source_thread_id=src_thread,
        source_message_ids_json=json.loads(src_msgs_raw) if src_msgs_raw else [],
        created_at=created_at,
        updated_at=updated_at,
        last_accessed_at=last_accessed_at,
        access_count=int(access_count),
        valid_from=valid_from,
        valid_to=valid_to,
        superseded_by=superseded_by,
        content_hash=content_hash,
    )


_SELECT_COLS = (
    "id, namespace, type, content, entities_json, confidence, importance, "
    "status, pinned, sensitivity, source_thread_id, source_message_ids_json, "
    "created_at, updated_at, last_accessed_at, access_count, "
    "valid_from, valid_to, superseded_by, content_hash, embedding"
)


# ---------------------------------------------------------------------------
# SQLiteMemoryStore
# ---------------------------------------------------------------------------


class SQLiteMemoryStore:
    """Production SQLite adapter implementing MemoryStorePort.

    All public methods are async; blocking SQLite calls are dispatched through
    asyncio.to_thread() so the FastAPI event loop is never blocked.

    Architecture:
        - _conn() returns a per-call connection with WAL mode and FK enforcement.
        - Migrations run on first instantiation; each migration is idempotent.
        - AuditLog is injected with _conn as the factory.
        - Secret guard runs before any content is written.
    """

    def __init__(
        self,
        db_path: str = "./storage/memory/memory.db",
        settings: MemorySettings | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings = settings or DEFAULT_SETTINGS
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._run_migrations()
        self.audit = AuditLog(self._conn)
        logger.info("SQLiteMemoryStore ready at %s", db_path)

    # ------------------------------------------------------------------
    # Connection and migration
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _run_migrations(self) -> None:
        conn = self._conn()
        with conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL, applied_at TEXT NOT NULL)"
            )
            current_versions = {
                row[0]
                for row in conn.execute("SELECT version FROM schema_version").fetchall()
            }
            for version, sql in _MIGRATIONS:
                if version not in current_versions:
                    conn.executescript(sql)
                    conn.execute(
                        "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
                        (version, datetime.now(UTC).isoformat()),
                    )
                    logger.info("Applied memory DB migration v%d", version)

    # ------------------------------------------------------------------
    # Namespace management (sync internals)
    # ------------------------------------------------------------------

    def _add_namespace(self, name: str) -> Namespace:
        conn = self._conn()
        existing = conn.execute(
            "SELECT id, name, created_at FROM namespaces WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            return Namespace(id=existing[0], name=existing[1], created_at=existing[2])
        ns = Namespace(name=name)
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO namespaces(id, name, created_at) VALUES (?, ?, ?)",
                (ns.id, ns.name, ns.created_at),
            )
        return ns

    def _get_namespace(self, name: str) -> Namespace | None:
        row = self._conn().execute(
            "SELECT id, name, created_at FROM namespaces WHERE name = ?", (name,)
        ).fetchone()
        return Namespace(id=row[0], name=row[1], created_at=row[2]) if row else None

    def _list_namespaces(self) -> list[Namespace]:
        rows = self._conn().execute(
            "SELECT id, name, created_at FROM namespaces ORDER BY created_at ASC"
        ).fetchall()
        return [Namespace(id=r[0], name=r[1], created_at=r[2]) for r in rows]

    def _delete_namespace(self, name: str) -> None:
        if name == "global":
            raise ValueError("The 'global' namespace cannot be deleted")
        conn = self._conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE namespace=? AND status='active'", (name,)
        ).fetchone()[0]
        if count > 0:
            raise ValueError(
                f"Cannot delete namespace '{name}': {count} active memories still belong to it"
            )
        with conn:
            conn.execute("DELETE FROM namespaces WHERE name = ?", (name,))

    # ------------------------------------------------------------------
    # Core CRUD (sync)
    # ------------------------------------------------------------------

    def _add(self, record: MemoryRecord, embedding: list[float] | None = None) -> MemoryRecord:
        is_safe, sanitised, pattern = scan_content(record.content)
        if not is_safe:
            self.audit.append(
                "secret_rejected",
                actor="secret_guard",
                payload={"pattern": pattern, "content_preview": record.content[:60]},
            )
            raise ValueError(
                f"Content rejected by secret guard: pattern '{pattern}' detected. "
                "Remove secrets before saving."
            )

        record.content = sanitised
        record.content_hash = _content_hash(record.content)
        record.updated_at = datetime.now(UTC).isoformat()

        blob = _pack_embedding(embedding) if embedding else None
        conn = self._conn()
        with conn:
            conn.execute(
                f"""INSERT INTO memories
                   ({_SELECT_COLS.replace('embedding', 'embedding')})
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id, record.namespace, record.type.value, record.content,
                    json.dumps(record.entities_json), record.confidence, record.importance,
                    record.status.value, int(record.pinned), record.sensitivity.value,
                    record.source_thread_id, json.dumps(record.source_message_ids_json),
                    record.created_at, record.updated_at, record.last_accessed_at,
                    record.access_count, record.valid_from, record.valid_to,
                    record.superseded_by, record.content_hash, blob,
                ),
            )

        self.audit.append("created", memory_id=record.id,
                          payload={"type": record.type.value, "namespace": record.namespace})
        return record

    def _get(self, memory_id: str) -> MemoryRecord | None:
        row = self._conn().execute(
            f"SELECT {_SELECT_COLS} FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def _update(self, memory_id: str, **fields: Any) -> MemoryRecord:
        record = self._get(memory_id)
        if record is None:
            raise KeyError(f"Memory '{memory_id}' not found")

        allowed = {
            "content", "type", "importance", "confidence", "status",
            "sensitivity", "valid_from", "valid_to", "superseded_by",
            "entities_json", "source_message_ids_json", "namespace",
        }
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"Fields not patchable: {bad}")

        now = datetime.now(UTC).isoformat()
        for k, v in fields.items():
            setattr(record, k, v)
        record.updated_at = now

        if "content" in fields:
            record.content_hash = _content_hash(record.content)

        conn = self._conn()
        with conn:
            conn.execute(
                """UPDATE memories SET
                   content=?, type=?, importance=?, confidence=?, status=?,
                   sensitivity=?, valid_from=?, valid_to=?, superseded_by=?,
                   entities_json=?, source_message_ids_json=?, namespace=?,
                   content_hash=?, updated_at=?
                   WHERE id=?""",
                (
                    record.content, record.type.value, record.importance,
                    record.confidence, record.status.value, record.sensitivity.value,
                    record.valid_from, record.valid_to, record.superseded_by,
                    json.dumps(record.entities_json),
                    json.dumps(record.source_message_ids_json),
                    record.namespace, record.content_hash, now, memory_id,
                ),
            )

        self.audit.append(
            "updated", memory_id=memory_id,
            payload={k: str(v) for k, v in fields.items()},
        )
        return record

    def _pin(self, memory_id: str, pinned: bool) -> None:
        conn = self._conn()
        with conn:
            conn.execute("UPDATE memories SET pinned=? WHERE id=?", (int(pinned), memory_id))

    def _approve(self, memory_id: str, actor: str) -> MemoryRecord:
        return self._update(memory_id, status=MemoryStatus.ACTIVE)

    def _reject(self, memory_id: str, actor: str) -> MemoryRecord:
        return self._update(memory_id, status=MemoryStatus.ARCHIVED)

    def _supersede(
        self, old_id: str, new_memory: MemoryRecord, actor: str, embedding: list[float] | None
    ) -> tuple[MemoryRecord, MemoryRecord]:
        now = datetime.now(UTC).isoformat()
        # Mark old as superseded
        old = self._update(
            old_id,
            status=MemoryStatus.SUPERSEDED,
            valid_to=now,
            superseded_by=new_memory.id,
        )
        # Insert new with pending status
        new_memory.status = MemoryStatus.PENDING
        new_memory.created_at = now
        new = self._add(new_memory, embedding)
        self.audit.append(
            "superseded", actor=actor, memory_id=old_id,
            payload={"new_memory_id": new.id},
        )
        return old, new

    def _forget(self, memory_id: str, actor: str) -> None:
        self._update(memory_id, status=MemoryStatus.FORGOTTEN)
        self.audit.append("forgotten", actor=actor, memory_id=memory_id)

    def _purge_forgotten(self) -> int:
        cutoff = (
            datetime.now(UTC) - timedelta(days=self.settings.purge_after_days)
        ).isoformat()
        conn = self._conn()
        with conn:
            ids_rows = conn.execute(
                "SELECT id FROM memories WHERE status='forgotten' AND updated_at < ?",
                (cutoff,),
            ).fetchall()
            ids = [r[0] for r in ids_rows]
            if ids:
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"DELETE FROM memories WHERE id IN ({placeholders})", ids
                )
        for mid in ids:
            self.audit.append("purged", memory_id=mid,
                              payload={"reason": "forgotten_expired"})
        logger.info("Purged %d forgotten memories", len(ids))
        return len(ids)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(self, filters: MemoryFilter) -> list[MemoryRecord]:
        clauses: list[str] = []
        params: list[Any] = []

        if filters.namespace:
            clauses.append("namespace = ?")
            params.append(filters.namespace)
        if filters.types:
            placeholders = ",".join("?" * len(filters.types))
            clauses.append(f"type IN ({placeholders})")
            params.extend(t.value for t in filters.types)
        if filters.statuses:
            placeholders = ",".join("?" * len(filters.statuses))
            clauses.append(f"status IN ({placeholders})")
            params.extend(s.value for s in filters.statuses)
        if filters.pinned is not None:
            clauses.append("pinned = ?")
            params.append(int(filters.pinned))
        if filters.sensitivity:
            placeholders = ",".join("?" * len(filters.sensitivity))
            clauses.append(f"sensitivity IN ({placeholders})")
            params.extend(s.value for s in filters.sensitivity)
        if filters.date_from:
            clauses.append("created_at >= ?")
            params.append(filters.date_from)
        if filters.date_to:
            clauses.append("created_at <= ?")
            params.append(filters.date_to)
        if filters.source_thread_id:
            clauses.append("source_thread_id = ?")
            params.append(filters.source_thread_id)
        if filters.text:
            clauses.append("content LIKE ?")
            params.append(f"%{filters.text}%")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = (
            f"SELECT {_SELECT_COLS} FROM memories {where} "
            f"ORDER BY importance DESC, created_at DESC "
            f"LIMIT ? OFFSET ?"
        )
        params.extend([filters.limit, filters.offset])
        rows = self._conn().execute(query, params).fetchall()
        return [_row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Hybrid search
    # ------------------------------------------------------------------

    def _search(
        self,
        query: str,
        embedding: list[float] | None,
        namespace: str,
        types: list[MemoryType] | None,
        top_k: int,
        include_global: bool,
    ) -> list[ScoredMemory]:
        w = self.settings.weights
        k = self.settings.rrf_k

        # Build namespace filter
        if include_global and namespace != "global":
            ns_filter = "m.namespace IN (?, 'global') AND m.namespace != ''"
            ns_params: list[Any] = [namespace]
        else:
            ns_filter = "m.namespace = ?"
            ns_params = [namespace]

        type_filter = ""
        type_params: list[Any] = []
        if types:
            placeholders = ",".join("?" * len(types))
            type_filter = f"AND m.type IN ({placeholders})"
            type_params = [t.value for t in types]

        # -- FTS5 branch --
        fts_scores: dict[str, int] = {}  # memory_id -> rank (0-based, lower = better)
        if query.strip():
            try:
                fts_q = _sanitise_fts_query(query.strip())
                fts_rows = self._conn().execute(
                    f"""SELECT m.id, rank FROM memories_fts
                        JOIN memories m ON memories_fts.rowid = m.rowid
                        WHERE memories_fts MATCH ?
                          AND m.status = 'active'
                          AND {ns_filter}
                          {type_filter}
                        ORDER BY rank
                        LIMIT ?""",
                    [fts_q, *ns_params, *type_params, top_k * 4],
                ).fetchall()
                for rank, (mid, _) in enumerate(fts_rows):
                    fts_scores[mid] = rank
            except Exception as exc:
                logger.debug("FTS5 search failed, skipping: %s", exc)

        # -- Vector branch --
        vec_scores: dict[str, float] = {}
        if embedding:
            # Fetch all active memories with embeddings in namespace
            vec_rows = self._conn().execute(
                f"""SELECT m.id, m.embedding FROM memories m
                    WHERE m.status = 'active'
                      AND m.embedding IS NOT NULL
                      AND {ns_filter}
                      {type_filter}""",
                [*ns_params, *type_params],
            ).fetchall()
            scored: list[tuple[str, float]] = []
            for mid, blob in vec_rows:
                stored_emb = _unpack_embedding(blob)
                if stored_emb:
                    sim = _cosine(embedding, stored_emb)
                    scored.append((mid, sim))
            scored.sort(key=lambda t: t[1], reverse=True)
            vec_scores = {mid: sim for mid, sim in scored[: top_k * 4]}

        # -- Candidate union --
        candidate_ids = set(fts_scores) | set(vec_scores)
        if not candidate_ids:
            return []

        # Fetch all candidates
        placeholders = ",".join("?" * len(candidate_ids))
        rows = self._conn().execute(
            f"SELECT {_SELECT_COLS} FROM memories WHERE id IN ({placeholders})",
            list(candidate_ids),
        ).fetchall()
        records = {row[0]: _row_to_record(row) for row in rows}

        # Vector ranks (sorted descending by sim, best=0)
        sorted_vec = sorted(vec_scores.items(), key=lambda t: t[1], reverse=True)
        vec_ranks = {mid: rank for rank, (mid, _) in enumerate(sorted_vec)}

        # RRF merge
        rrf: dict[str, float] = {}
        for mid in candidate_ids:
            fts_part = 1.0 / (k + fts_scores[mid]) if mid in fts_scores else 0.0
            vec_part = 1.0 / (k + vec_ranks[mid]) if mid in vec_ranks else 0.0
            rrf[mid] = fts_part + vec_part

        max_rrf = max(rrf.values()) if rrf else 1.0

        # Final score
        results: list[ScoredMemory] = []
        for mid, record in records.items():
            relevance = rrf[mid] / max_rrf
            importance = record.importance
            recency = _recency_decay(
                record.last_accessed_at, record.created_at,
                self.settings.recency_half_life_days,
            )
            score = (
                w.relevance * relevance
                + w.importance * importance
                + w.recency * recency
                + (w.pin_boost if record.pinned else 0.0)
            )
            results.append(
                ScoredMemory(
                    memory=record,
                    score=score,
                    fts_rank=fts_scores.get(mid, -1),
                    vector_score=vec_scores.get(mid, 0.0),
                    rrf_score=rrf[mid],
                )
            )

        results.sort(key=lambda s: s.score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Touch
    # ------------------------------------------------------------------

    def _touch(self, ids: list[str]) -> None:
        if not ids:
            return
        now = datetime.now(UTC).isoformat()
        conn = self._conn()
        with conn:
            for mid in ids:
                conn.execute(
                    "UPDATE memories SET last_accessed_at=?, access_count=access_count+1 "
                    "WHERE id=?",
                    (now, mid),
                )

    # ------------------------------------------------------------------
    # Export / import / backup / restore
    # ------------------------------------------------------------------

    def _export_all(self) -> dict[str, Any]:
        conn = self._conn()
        ns_rows = conn.execute("SELECT id, name, created_at FROM namespaces").fetchall()
        mem_rows = conn.execute(f"SELECT {_SELECT_COLS} FROM memories").fetchall()
        namespaces = [{"id": r[0], "name": r[1], "created_at": r[2]} for r in ns_rows]
        memories = []
        for row in mem_rows:
            r = _row_to_record(row)
            memories.append(r.model_dump())
        export = {
            "schema_version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
            "namespaces": namespaces,
            "memories": memories,
        }
        self.audit.append("exported", payload={"count": len(memories)})
        return export

    def _import_all(self, data: dict[str, Any], actor: str) -> int:
        inserted = 0
        for ns_data in data.get("namespaces", []):
            self._add_namespace(ns_data["name"])
        for mem_data in data.get("memories", []):
            content = mem_data.get("content", "")
            ch = _content_hash(content)
            ns = mem_data.get("namespace", "global")
            conn = self._conn()
            exists = conn.execute(
                "SELECT id FROM memories WHERE namespace=? AND content_hash=?",
                (ns, ch),
            ).fetchone()
            if exists:
                continue
            record = MemoryRecord(**{k: v for k, v in mem_data.items() if k != "id"})
            record.id = str(uuid.uuid4())
            self._add(record)
            inserted += 1
        self.audit.append("imported", actor=actor, payload={"inserted": inserted})
        return inserted

    def _backup(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        src = self._conn()
        dst = sqlite3.connect(path)
        try:
            src.backup(dst)
        finally:
            dst.close()
        self.audit.append("backup", payload={"path": path})
        logger.info("Memory DB backed up to %s", path)

    def _restore(self, path: str) -> None:
        if not Path(path).exists():
            raise FileNotFoundError(f"Backup file not found: {path}")
        src = sqlite3.connect(path)
        dst = self._conn()
        try:
            src.backup(dst)
        finally:
            src.close()
        self.audit.append("restore", payload={"path": path})
        logger.info("Memory DB restored from %s", path)

    # ------------------------------------------------------------------
    # History (supersede chain)
    # ------------------------------------------------------------------

    def _get_history(self, memory_id: str) -> list[MemoryRecord]:
        """Follow superseded_by links backwards to reconstruct the version chain."""
        result: list[MemoryRecord] = []
        current_id: str | None = memory_id
        seen: set[str] = set()
        while current_id and current_id not in seen:
            seen.add(current_id)
            record = self._get(current_id)
            if record is None:
                break
            result.append(record)
            current_id = record.superseded_by
        return result

    # ------------------------------------------------------------------
    # Public async API (MemoryStorePort)
    # ------------------------------------------------------------------

    async def add_namespace(self, name: str) -> Namespace:
        return await asyncio.to_thread(self._add_namespace, name)

    async def get_namespace(self, name: str) -> Namespace | None:
        return await asyncio.to_thread(self._get_namespace, name)

    async def list_namespaces(self) -> list[Namespace]:
        return await asyncio.to_thread(self._list_namespaces)

    async def delete_namespace(self, name: str) -> None:
        await asyncio.to_thread(self._delete_namespace, name)

    async def add(
        self,
        record: MemoryRecord,
        embedding: list[float] | None = None,
    ) -> MemoryRecord:
        return await asyncio.to_thread(self._add, record, embedding)

    async def get(self, memory_id: str) -> MemoryRecord | None:
        return await asyncio.to_thread(self._get, memory_id)

    async def update(self, memory_id: str, **fields: Any) -> MemoryRecord:
        return await asyncio.to_thread(self._update, memory_id, **fields)

    async def pin(self, memory_id: str, pinned: bool) -> None:
        await asyncio.to_thread(self._pin, memory_id, pinned)

    async def approve(self, memory_id: str, actor: str = "user") -> MemoryRecord:
        record = await asyncio.to_thread(self._approve, memory_id, actor)
        self.audit.append("approved", actor=actor, memory_id=memory_id)
        return record

    async def reject(self, memory_id: str, actor: str = "user") -> MemoryRecord:
        record = await asyncio.to_thread(self._reject, memory_id, actor)
        self.audit.append("rejected", actor=actor, memory_id=memory_id)
        return record

    async def supersede(
        self,
        old_id: str,
        new_memory: MemoryRecord,
        actor: str = "system",
        embedding: list[float] | None = None,
    ) -> tuple[MemoryRecord, MemoryRecord]:
        return await asyncio.to_thread(self._supersede, old_id, new_memory, actor, embedding)

    async def forget(self, memory_id: str, actor: str = "user") -> None:
        await asyncio.to_thread(self._forget, memory_id, actor)

    async def purge_forgotten(self) -> int:
        return await asyncio.to_thread(self._purge_forgotten)

    async def list(self, filters: MemoryFilter) -> list[MemoryRecord]:
        return await asyncio.to_thread(self._list, filters)

    async def search(
        self,
        query: str,
        embedding: list[float] | None,
        namespace: str,
        types: list[MemoryType] | None = None,
        top_k: int = 5,
        include_global: bool = True,
    ) -> list[ScoredMemory]:
        return await asyncio.to_thread(
            self._search, query, embedding, namespace, types, top_k, include_global
        )

    async def touch(self, ids: list[str]) -> None:
        await asyncio.to_thread(self._touch, ids)

    async def get_history(self, memory_id: str) -> list[MemoryRecord]:
        return await asyncio.to_thread(self._get_history, memory_id)

    async def list_audit(
        self,
        limit: int = 100,
        offset: int = 0,
        memory_id: str | None = None,
    ) -> list[MemoryEvent]:
        return await self.audit.alist_events(limit, offset, memory_id)

    async def verify_audit(self) -> tuple[bool, str]:
        return await self.audit.averify()

    async def export_all(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._export_all)

    async def import_all(self, data: dict[str, Any], actor: str = "import") -> int:
        return await asyncio.to_thread(self._import_all, data, actor)

    async def backup(self, path: str) -> None:
        await asyncio.to_thread(self._backup, path)

    async def restore(self, path: str) -> None:
        await asyncio.to_thread(self._restore, path)

    # ------------------------------------------------------------------
    # Embedding helpers exposed for use by the extraction pipeline
    # ------------------------------------------------------------------

    def find_by_hash(self, namespace: str, content_hash: str) -> MemoryRecord | None:
        """Synchronous lookup used during deduplication in the extractor."""
        row = self._conn().execute(
            f"SELECT {_SELECT_COLS} FROM memories WHERE namespace=? AND content_hash=?",
            (namespace, content_hash),
        ).fetchone()
        return _row_to_record(row) if row else None

    def get_active_with_embeddings(
        self, namespace: str, include_global: bool = True
    ) -> list[tuple[MemoryRecord, list[float]]]:
        """Return (record, embedding) pairs for cosine comparisons."""
        if include_global and namespace != "global":
            rows = self._conn().execute(
                f"SELECT {_SELECT_COLS} FROM memories "
                "WHERE status='active' AND embedding IS NOT NULL "
                "AND namespace IN (?, 'global')",
                (namespace,),
            ).fetchall()
        else:
            rows = self._conn().execute(
                f"SELECT {_SELECT_COLS} FROM memories "
                "WHERE status='active' AND embedding IS NOT NULL AND namespace=?",
                (namespace,),
            ).fetchall()
        result: list[tuple[MemoryRecord, list[float]]] = []
        for row in rows:
            emb_blob = row[-1]
            emb = _unpack_embedding(emb_blob)
            if emb:
                result.append((_row_to_record(row), emb))
        return result

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate counts per status and type."""
        conn = self._conn()
        status_rows = conn.execute(
            "SELECT status, COUNT(*) FROM memories GROUP BY status"
        ).fetchall()
        type_rows = conn.execute(
            "SELECT type, COUNT(*) FROM memories WHERE status='active' GROUP BY type"
        ).fetchall()
        return {
            "by_status": {r[0]: r[1] for r in status_rows},
            "active_by_type": {r[0]: r[1] for r in type_rows},
            "total": sum(r[1] for r in status_rows),
        }
