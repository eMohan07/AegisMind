from __future__ import annotations

import math
import pytest

from aegismind_core.memory.sqlite_store import SQLiteMemoryStore
import sys
from pathlib import Path

# Ensure tests/eval directory is on sys.path
_eval_dir = str(Path(__file__).parent)
if _eval_dir not in sys.path:
    sys.path.insert(0, _eval_dir)

from memory_recall import GOLDEN_MEMORY_FIXTURES, run_memory_recall_benchmark


class DeterministicEmbedder:
    """Simple deterministic 64-dim unit vector embedder for reproducible eval tests."""

    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension

    async def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        words = text.lower().split()
        for i, word in enumerate(words):
            h = hash(word) % self.dimension
            vec[h] += 1.0 / (i + 1)
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            return [v / norm for v in vec]
        return vec


@pytest.fixture
def eval_store(tmp_path: pytest.TempPathFactory) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path=str(tmp_path / "eval_memory.db"))


@pytest.mark.asyncio
async def test_golden_memory_recall_benchmark(eval_store: SQLiteMemoryStore) -> None:
    """Evaluate retrieval quality across 15 golden fixtures for Recall@3 and MRR."""
    embedder = DeterministicEmbedder(dimension=64)

    summary = await run_memory_recall_benchmark(
        store=eval_store,
        embedder_fn=embedder.embed,
        fixtures=GOLDEN_MEMORY_FIXTURES,
        namespace="eval-bench",
    )

    assert summary.total_queries == 15
    # High-recall target: at least 80% of queries retrieve the expected memory in top 3
    assert summary.recall_at_3 >= 0.80, (
        f"Recall@3 {summary.recall_at_3} fell below threshold 0.80. "
        f"Hits: {summary.hits_at_3}/{summary.total_queries}"
    )
    # MRR target: average reciprocal rank >= 0.60
    assert summary.mrr >= 0.60, f"MRR {summary.mrr} fell below threshold 0.60"
