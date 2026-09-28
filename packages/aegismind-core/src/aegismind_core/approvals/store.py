from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

from aegismind_core.approvals.models import Proposal, ProposalStatus, RiskLevel

logger = logging.getLogger(__name__)


class ApprovalStore:
    """SQLite-backed store for approval proposals at .aegismind/approvals.db."""

    def __init__(self, db_path: str = ".aegismind/approvals.db") -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    tool_name TEXT NOT NULL,
                    args TEXT NOT NULL DEFAULT '{}',
                    edited_args TEXT,
                    risk TEXT NOT NULL DEFAULT 'low',
                    reasoning TEXT NOT NULL DEFAULT '',
                    source_refs TEXT NOT NULL DEFAULT '[]',
                    preview TEXT NOT NULL DEFAULT '',
                    tainted INTEGER NOT NULL DEFAULT 0,
                    taint_sources TEXT NOT NULL DEFAULT '[]',
                    decision_reason TEXT,
                    result TEXT,
                    created_at_ts REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
                CREATE INDEX IF NOT EXISTS idx_proposals_created ON proposals(created_at_ts);
            """)
        logger.info("Approval database initialized at %s", self.db_path)

    def create(self, proposal: Proposal) -> Proposal:
        """Insert a new proposal into the store."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO proposals (
                    id, created_at, expires_at, status, tool_name, args,
                    edited_args, risk, reasoning, source_refs, preview,
                    tainted, taint_sources, decision_reason, result, created_at_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    proposal.id,
                    proposal.created_at,
                    proposal.expires_at,
                    proposal.status.value,
                    proposal.tool_name,
                    json.dumps(proposal.args),
                    json.dumps(proposal.edited_args) if proposal.edited_args else None,
                    proposal.risk.value,
                    proposal.reasoning,
                    json.dumps(proposal.source_refs),
                    proposal.preview,
                    1 if proposal.tainted else 0,
                    json.dumps(proposal.taint_sources),
                    proposal.decision_reason,
                    proposal.result,
                    datetime.now(UTC).timestamp(),
                ),
            )
        logger.info("Created proposal %s for tool %s", proposal.id, proposal.tool_name)
        return proposal

    def get(self, proposal_id: str) -> Proposal | None:
        """Retrieve a proposal by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_proposal(row)

    def list_by_status(self, status: str | None = None) -> list[Proposal]:
        """List proposals, optionally filtered by status."""
        with sqlite3.connect(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM proposals ORDER BY created_at DESC"
                ).fetchall()
        return [self._row_to_proposal(row) for row in rows]

    def update(self, proposal: Proposal) -> None:
        """Update an existing proposal."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE proposals SET
                    status = ?,
                    expires_at = ?,
                    edited_args = ?,
                    risk = ?,
                    decision_reason = ?,
                    result = ?
                WHERE id = ?""",
                (
                    proposal.status.value,
                    proposal.expires_at,
                    json.dumps(proposal.edited_args) if proposal.edited_args else None,
                    proposal.risk.value,
                    proposal.decision_reason,
                    proposal.result,
                    proposal.id,
                ),
            )
        logger.info("Updated proposal %s status=%s", proposal.id, proposal.status.value)

    def expire_old(self) -> int:
        """Mark expired proposals as EXPIRED. Returns count of expired proposals."""
        now = datetime.now(UTC)
        expired_count = 0
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, expires_at, status FROM proposals WHERE status = 'pending'"
            ).fetchall()
            for row in rows:
                proposal_id, expires_at, _ = row
                if now > datetime.fromisoformat(expires_at):
                    conn.execute(
                        "UPDATE proposals SET status = ? WHERE id = ?",
                        (ProposalStatus.EXPIRED.value, proposal_id),
                    )
                    expired_count += 1
        if expired_count > 0:
            logger.info("Expired %d pending proposals", expired_count)
        return expired_count

    def _row_to_proposal(self, row: tuple[Any, ...]) -> Proposal:
        """Convert a database row to a Proposal model."""
        return Proposal(
            id=row[0],
            created_at=row[1],
            expires_at=row[2],
            status=ProposalStatus(row[3]),
            tool_name=row[4],
            args=json.loads(row[5]) if isinstance(row[5], str) else row[5],
            edited_args=json.loads(row[6]) if row[6] and isinstance(row[6], str) else None,
            risk=RiskLevel(row[7]),
            reasoning=row[8],
            source_refs=json.loads(row[9]) if isinstance(row[9], str) else row[9],
            preview=row[10],
            tainted=bool(row[11]),
            taint_sources=json.loads(row[12]) if isinstance(row[12], str) else row[12],
            decision_reason=row[13],
            result=row[14],
        )
