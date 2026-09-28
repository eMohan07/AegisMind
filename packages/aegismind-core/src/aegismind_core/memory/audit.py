from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

from aegismind_core.memory.models import MemoryEvent

logger = logging.getLogger(__name__)

_GENESIS_HASH = "0" * 64


def _compute_hash(
    seq: int,
    ts: str,
    event: str,
    memory_id: str | None,
    actor: str,
    payload: dict[str, Any],
    prev_hash: str,
) -> str:
    """Compute the SHA-256 hash for one audit event row.

    All fields are canonicalised via JSON (sorted keys, ASCII-safe) so the
    hash is deterministic regardless of platform or Python version.
    """
    canonical = json.dumps(
        {
            "seq": seq,
            "ts": ts,
            "event": event,
            "memory_id": memory_id,
            "actor": actor,
            "payload": payload,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class AuditLog:
    """Append-only, SHA-256 hash-chained audit log.

    Backed by the *memory_events* table in the same SQLite database as the
    rest of the memory store. The table has BEFORE UPDATE and BEFORE DELETE
    triggers that RAISE(ABORT, ...) to enforce immutability at the DB level.
    """

    def __init__(self, conn_factory: Any) -> None:
        # conn_factory() must return a live sqlite3.Connection (no isolation_level)
        self._conn_factory = conn_factory

    # ------------------------------------------------------------------
    # Synchronous core (called via asyncio.to_thread from async callers)
    # ------------------------------------------------------------------

    def append(
        self,
        event: str,
        actor: str = "system",
        memory_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        """Append one event, computing and storing the hash chain link."""
        conn: sqlite3.Connection = self._conn_factory()
        ts = datetime.now(UTC).isoformat()
        safe_payload = payload or {}

        with conn:
            row = conn.execute(
                "SELECT seq, hash FROM memory_events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            if row:
                seq = row[0] + 1
                prev_hash: str = row[1]
            else:
                seq = 1
                prev_hash = _GENESIS_HASH

            this_hash = _compute_hash(seq, ts, event, memory_id, actor, safe_payload, prev_hash)

            conn.execute(
                """INSERT INTO memory_events
                   (seq, ts, event, memory_id, actor, payload, prev_hash, hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    seq, ts, event, memory_id, actor,
                    json.dumps(safe_payload, ensure_ascii=True, sort_keys=True),
                    prev_hash, this_hash,
                ),
            )

        logger.debug("audit: seq=%d event=%s memory_id=%s", seq, event, memory_id)
        return MemoryEvent(
            seq=seq, ts=ts, event=event, memory_id=memory_id,
            actor=actor, payload=safe_payload, prev_hash=prev_hash, hash=this_hash,
        )

    def verify(self) -> tuple[bool, str]:
        """Walk every row in chain order and recompute each hash.

        Returns:
            (True, "") if the chain is intact.
            (False, human_readable_error) on the first broken link.
        """
        conn: sqlite3.Connection = self._conn_factory()
        rows = conn.execute(
            "SELECT seq, ts, event, memory_id, actor, payload, prev_hash, hash "
            "FROM memory_events ORDER BY seq ASC"
        ).fetchall()

        if not rows:
            return True, ""

        expected_prev = _GENESIS_HASH
        for row in rows:
            seq, ts, event, memory_id, actor, payload_raw, stored_prev, stored_hash = row
            try:
                payload: dict[str, Any] = json.loads(payload_raw)
            except Exception as exc:
                return False, f"seq={seq}: payload JSON parse error: {exc}"

            if stored_prev != expected_prev:
                return False, (
                    f"seq={seq}: prev_hash mismatch "
                    f"(stored={stored_prev!r}, expected={expected_prev!r})"
                )

            expected_hash = _compute_hash(
                seq, ts, event, memory_id, actor, payload, stored_prev
            )
            if expected_hash != stored_hash:
                return False, (
                    f"seq={seq}: hash mismatch "
                    f"(stored={stored_hash!r}, recomputed={expected_hash!r})"
                )

            expected_prev = stored_hash

        return True, ""

    def list_events(
        self,
        limit: int = 100,
        offset: int = 0,
        memory_id: str | None = None,
    ) -> list[MemoryEvent]:
        """Return events newest-first, optionally filtered by memory_id."""
        conn: sqlite3.Connection = self._conn_factory()
        if memory_id:
            rows = conn.execute(
                "SELECT seq, ts, event, memory_id, actor, payload, prev_hash, hash "
                "FROM memory_events WHERE memory_id = ? "
                "ORDER BY seq DESC LIMIT ? OFFSET ?",
                (memory_id, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT seq, ts, event, memory_id, actor, payload, prev_hash, hash "
                "FROM memory_events ORDER BY seq DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [
            MemoryEvent(
                seq=r[0], ts=r[1], event=r[2], memory_id=r[3],
                actor=r[4], payload=json.loads(r[5]),
                prev_hash=r[6], hash=r[7],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Async wrappers
    # ------------------------------------------------------------------

    async def aappend(
        self,
        event: str,
        actor: str = "system",
        memory_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        return await asyncio.to_thread(self.append, event, actor, memory_id, payload)

    async def averify(self) -> tuple[bool, str]:
        return await asyncio.to_thread(self.verify)

    async def alist_events(
        self,
        limit: int = 100,
        offset: int = 0,
        memory_id: str | None = None,
    ) -> list[MemoryEvent]:
        return await asyncio.to_thread(self.list_events, limit, offset, memory_id)
