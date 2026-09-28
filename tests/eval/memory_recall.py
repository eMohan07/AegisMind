from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aegismind_core.memory.models import MemoryRecord, MemoryStatus, MemoryType
from aegismind_core.memory.sqlite_store import SQLiteMemoryStore

logger = logging.getLogger(__name__)


class MemoryRecallFixture(BaseModel):
    """A test fixture for long-term memory retrieval evaluation."""

    model_config = ConfigDict(frozen=True)

    fixture_id: str
    memory_content: str
    memory_type: MemoryType
    entities: list[str]
    importance: float = 0.7
    query: str
    expected_fixture_id: str


class MemoryRecallSummary(BaseModel):
    """Aggregated evaluation results for memory recall benchmark."""

    model_config = ConfigDict(frozen=True)

    total_queries: int
    recall_at_3: float
    mrr: float
    hits_at_1: int
    hits_at_3: int
    details: list[dict[str, Any]] = Field(default_factory=list)


# 15 golden fixtures covering user preferences, episodic events, semantic knowledge, and procedural instructions
GOLDEN_MEMORY_FIXTURES: list[MemoryRecallFixture] = [
    MemoryRecallFixture(
        fixture_id="fix-pref-01",
        memory_content="User prefers code examples written in Python rather than TypeScript.",
        memory_type=MemoryType.PREFERENCE,
        entities=["Python", "TypeScript"],
        importance=0.9,
        query="What language should I use for code snippets?",
        expected_fixture_id="fix-pref-01",
    ),
    MemoryRecallFixture(
        fixture_id="fix-pref-02",
        memory_content="User prefers dark mode and high-contrast color schemes across all interfaces.",
        memory_type=MemoryType.PREFERENCE,
        entities=["dark mode", "UI"],
        importance=0.8,
        query="What UI theme does the user prefer?",
        expected_fixture_id="fix-pref-02",
    ),
    MemoryRecallFixture(
        fixture_id="fix-pref-03",
        memory_content="User wants concise answers without conversational pleasantries or preamble.",
        memory_type=MemoryType.PREFERENCE,
        entities=["concise", "style"],
        importance=0.85,
        query="How does the user like their answers formatted?",
        expected_fixture_id="fix-pref-03",
    ),
    MemoryRecallFixture(
        fixture_id="fix-sem-01",
        memory_content="Project AegisMind uses SQLite with WAL mode for zero-leakage local storage.",
        memory_type=MemoryType.SEMANTIC,
        entities=["AegisMind", "SQLite", "WAL"],
        importance=0.95,
        query="What database engine and mode does AegisMind use?",
        expected_fixture_id="fix-sem-01",
    ),
    MemoryRecallFixture(
        fixture_id="fix-sem-02",
        memory_content="The primary tenant identifier for corporate development is corp-default.",
        memory_type=MemoryType.SEMANTIC,
        entities=["tenant", "corp-default"],
        importance=0.75,
        query="What is the default corporate tenant ID?",
        expected_fixture_id="fix-sem-02",
    ),
    MemoryRecallFixture(
        fixture_id="fix-sem-03",
        memory_content="The vector embeddings are normalized unit vectors of 64 float dimensions.",
        memory_type=MemoryType.SEMANTIC,
        entities=["embeddings", "vector", "dimensions"],
        importance=0.7,
        query="What dimension are the vector embeddings?",
        expected_fixture_id="fix-sem-03",
    ),
    MemoryRecallFixture(
        fixture_id="fix-sem-04",
        memory_content="Ollama local API endpoint runs on port 11434 with llama3.2 model.",
        memory_type=MemoryType.SEMANTIC,
        entities=["Ollama", "port 11434", "llama3.2"],
        importance=0.9,
        query="Which port and model does local Ollama use?",
        expected_fixture_id="fix-sem-04",
    ),
    MemoryRecallFixture(
        fixture_id="fix-epi-01",
        memory_content="On September 28, the team completed migration of long-term memory to SQLiteMemoryStore.",
        memory_type=MemoryType.EPISODIC,
        entities=["migration", "SQLiteMemoryStore", "September 28"],
        importance=0.85,
        query="When was the long-term memory migration completed?",
        expected_fixture_id="fix-epi-01",
    ),
    MemoryRecallFixture(
        fixture_id="fix-epi-02",
        memory_content="Yesterday user debugged an issue where WAL uncommitted pages were missing in backups.",
        memory_type=MemoryType.EPISODIC,
        entities=["WAL", "backup", "debug"],
        importance=0.75,
        query="What backup issue was debugged yesterday?",
        expected_fixture_id="fix-epi-02",
    ),
    MemoryRecallFixture(
        fixture_id="fix-epi-03",
        memory_content="During the security review, seven regex patterns were added to the secret guard scanner.",
        memory_type=MemoryType.EPISODIC,
        entities=["security review", "secret guard", "regex"],
        importance=0.8,
        query="How many regex patterns were added to the secret guard?",
        expected_fixture_id="fix-epi-03",
    ),
    MemoryRecallFixture(
        fixture_id="fix-epi-04",
        memory_content="Alice deployed Lens UI v2 with modern obsidian theme and responsive tabs.",
        memory_type=MemoryType.EPISODIC,
        entities=["Alice", "Lens UI", "obsidian theme"],
        importance=0.7,
        query="Who deployed Lens UI v2 and with what theme?",
        expected_fixture_id="fix-epi-04",
    ),
    MemoryRecallFixture(
        fixture_id="fix-proc-01",
        memory_content="To run backend unit tests, invoke uv run pytest packages/aegismind-core/tests.",
        memory_type=MemoryType.PROCEDURAL,
        entities=["uv run", "pytest", "tests"],
        importance=0.9,
        query="How do I run the backend unit tests?",
        expected_fixture_id="fix-proc-01",
    ),
    MemoryRecallFixture(
        fixture_id="fix-proc-02",
        memory_content="To approve a memory record, send a PATCH request with status active.",
        memory_type=MemoryType.PROCEDURAL,
        entities=["approve", "PATCH", "status active"],
        importance=0.85,
        query="How do I approve a pending memory record via API?",
        expected_fixture_id="fix-proc-02",
    ),
    MemoryRecallFixture(
        fixture_id="fix-proc-03",
        memory_content="To create a WAL-safe SQLite backup, call the native sqlite3 connection backup API.",
        memory_type=MemoryType.PROCEDURAL,
        entities=["WAL", "backup", "sqlite3"],
        importance=0.8,
        query="How should a backup be taken with SQLite WAL mode?",
        expected_fixture_id="fix-proc-03",
    ),
    MemoryRecallFixture(
        fixture_id="fix-proc-04",
        memory_content="To verify the audit log, traverse memory_events and recompute the SHA-256 hash chain.",
        memory_type=MemoryType.PROCEDURAL,
        entities=["audit log", "SHA-256", "hash chain"],
        importance=0.85,
        query="How is the audit log verified against tampering?",
        expected_fixture_id="fix-proc-04",
    ),
]


async def run_memory_recall_benchmark(
    store: SQLiteMemoryStore,
    embedder_fn: Callable[[str], Awaitable[list[float]]] | None = None,
    fixtures: list[MemoryRecallFixture] | None = None,
    namespace: str = "eval-bench",
) -> MemoryRecallSummary:
    """Ingest test fixtures and evaluate Recall@3 and MRR across queries."""
    bench_fixtures = fixtures or GOLDEN_MEMORY_FIXTURES
    created_map: dict[str, str] = {}  # fixture_id -> db memory_id

    # 1. Ingest all fixture memories into store
    for fix in bench_fixtures:
        emb: list[float] | None = None
        if embedder_fn:
            emb = await embedder_fn(fix.memory_content)

        record = MemoryRecord(
            namespace=namespace,
            type=fix.memory_type,
            content=fix.memory_content,
            entities=fix.entities,
            importance=fix.importance,
            status=MemoryStatus.ACTIVE,
        )
        saved = await store.add(record, embedding=emb)
        await store.approve(saved.id)
        created_map[fix.fixture_id] = saved.id

    # 2. Query each fixture and compute metrics
    hits_at_1 = 0
    hits_at_3 = 0
    reciprocal_ranks: list[float] = []
    details: list[dict[str, Any]] = []

    for fix in bench_fixtures:
        expected_db_id = created_map[fix.expected_fixture_id]
        query_emb: list[float] | None = None
        if embedder_fn:
            query_emb = await embedder_fn(fix.query)

        results = await store.search(
            query=fix.query,
            embedding=query_emb,
            namespace=namespace,
            top_k=5,
        )

        ranked_ids = [res.memory.id for res in results]
        rank = -1
        if expected_db_id in ranked_ids:
            rank = ranked_ids.index(expected_db_id) + 1

        rr = 1.0 / rank if rank > 0 else 0.0
        reciprocal_ranks.append(rr)

        if rank == 1:
            hits_at_1 += 1
        if 1 <= rank <= 3:
            hits_at_3 += 1

        details.append({
            "fixture_id": fix.fixture_id,
            "query": fix.query,
            "expected_db_id": expected_db_id,
            "found_rank": rank,
            "rr": rr,
        })

    n = len(bench_fixtures)
    recall_at_3 = hits_at_3 / n if n > 0 else 0.0
    mrr = sum(reciprocal_ranks) / n if n > 0 else 0.0

    return MemoryRecallSummary(
        total_queries=n,
        recall_at_3=round(recall_at_3, 4),
        mrr=round(mrr, 4),
        hits_at_1=hits_at_1,
        hits_at_3=hits_at_3,
        details=details,
    )
