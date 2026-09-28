from __future__ import annotations

import json

import pytest

from aegismind_core.memory.extractor import (
    ExtractionResult,
    MemoryExtractor,
    _format_messages,
    _parse_candidates,
)
from aegismind_core.memory.models import MemoryRecord, MemoryStatus, MemoryType
from aegismind_core.memory.sqlite_store import SQLiteMemoryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: pytest.TempPathFactory) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path=str(tmp_path / "extractor_test.db"))


def _make_llm(candidates: list[dict]) -> object:
    """Return an async callable that always returns *candidates* as JSON."""

    async def _fn(_prompt: str) -> str:
        return json.dumps(candidates)

    return _fn


def _make_extractor(
    store: SQLiteMemoryStore, candidates: list[dict]
) -> MemoryExtractor:
    return MemoryExtractor(store=store, llm_fn=_make_llm(candidates))


SAMPLE_MESSAGES = [
    {"role": "user", "content": "I prefer dark mode in all my apps."},
    {"role": "assistant", "content": "Noted, I will remember your dark mode preference."},
    {"role": "user", "content": "Also I usually work from 9 AM to 6 PM IST."},
    {"role": "assistant", "content": "Got it, I will keep that in mind."},
]

SAMPLE_CANDIDATES = [
    {
        "content": "The user prefers dark mode in all apps.",
        "type": "semantic",
        "importance": 0.7,
        "confidence": 0.95,
        "entities": ["dark mode"],
    },
    {
        "content": "The user typically works from 9 AM to 6 PM IST.",
        "type": "episodic",
        "importance": 0.6,
        "confidence": 0.90,
        "entities": ["IST"],
    },
]


# ---------------------------------------------------------------------------
# 1. Basic extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_produces_pending_records(store: SQLiteMemoryStore) -> None:
    extractor = _make_extractor(store, SAMPLE_CANDIDATES)
    result = await extractor.extract_from_thread(SAMPLE_MESSAGES)

    assert isinstance(result, ExtractionResult)
    assert len(result.extracted) == 2
    assert result.skipped_duplicate == 0

    for mem in result.extracted:
        assert mem.status == MemoryStatus.PENDING
        assert mem.namespace == "global"


@pytest.mark.asyncio
async def test_extraction_correct_types(store: SQLiteMemoryStore) -> None:
    extractor = _make_extractor(store, SAMPLE_CANDIDATES)
    result = await extractor.extract_from_thread(SAMPLE_MESSAGES)

    types = {m.content[:20]: m.type for m in result.extracted}
    assert any(t == MemoryType.SEMANTIC for t in types.values())
    assert any(t == MemoryType.EPISODIC for t in types.values())


@pytest.mark.asyncio
async def test_extraction_respects_namespace(store: SQLiteMemoryStore) -> None:
    extractor = _make_extractor(store, SAMPLE_CANDIDATES)
    result = await extractor.extract_from_thread(SAMPLE_MESSAGES, namespace="workspace")

    for mem in result.extracted:
        assert mem.namespace == "workspace"


@pytest.mark.asyncio
async def test_extraction_attaches_source_thread_id(store: SQLiteMemoryStore) -> None:
    extractor = _make_extractor(store, SAMPLE_CANDIDATES)
    result = await extractor.extract_from_thread(
        SAMPLE_MESSAGES, source_thread_id="thread-42"
    )
    for mem in result.extracted:
        assert mem.source_thread_id == "thread-42"


# ---------------------------------------------------------------------------
# 2. Private thread guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_private_thread_skips_extraction(store: SQLiteMemoryStore) -> None:
    # Even if the LLM would return candidates, private=True must produce nothing
    extractor = _make_extractor(store, SAMPLE_CANDIDATES)
    result = await extractor.extract_from_thread(SAMPLE_MESSAGES, private=True)

    assert result.extracted == []
    assert result.skipped_duplicate == 0
    assert result.skipped_contradiction == 0


# ---------------------------------------------------------------------------
# 3. Empty / no-message input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_messages_returns_empty(store: SQLiteMemoryStore) -> None:
    extractor = _make_extractor(store, SAMPLE_CANDIDATES)
    result = await extractor.extract_from_thread([])
    assert result.extracted == []


@pytest.mark.asyncio
async def test_whitespace_only_messages_returns_empty(store: SQLiteMemoryStore) -> None:
    extractor = _make_extractor(store, SAMPLE_CANDIDATES)
    msgs = [{"role": "user", "content": "   "}, {"role": "assistant", "content": ""}]
    result = await extractor.extract_from_thread(msgs)
    assert result.extracted == []


# ---------------------------------------------------------------------------
# 4. Deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_by_content_hash(store: SQLiteMemoryStore) -> None:
    """If the same fact already exists in the store, it must be skipped."""
    # Pre-insert the same content
    existing = MemoryRecord(
        namespace="global",
        content="The user prefers dark mode in all apps.",
        type=MemoryType.SEMANTIC,
    )
    saved = await store.add(existing)
    await store.approve(saved.id)

    # Now try to extract the same content
    extractor = _make_extractor(store, [SAMPLE_CANDIDATES[0]])
    result = await extractor.extract_from_thread(SAMPLE_MESSAGES[:2])

    # The duplicate should be skipped
    assert result.skipped_duplicate >= 1
    assert len(result.extracted) == 0


@pytest.mark.asyncio
async def test_dedup_with_vector_similarity(store: SQLiteMemoryStore) -> None:
    """Memories with cosine similarity >= dedup_threshold must be skipped."""
    from aegismind_core.memory.settings import MemorySettings

    settings = MemorySettings(dedup_similarity_threshold=0.90)
    extractor = MemoryExtractor(
        store=store, llm_fn=_make_llm([SAMPLE_CANDIDATES[0]]), settings=settings
    )

    # Store an existing memory with an embedding very close to the candidate's
    existing = MemoryRecord(
        namespace="global",
        content="User likes dark mode for all applications.",
        type=MemoryType.SEMANTIC,
    )
    embedding_a = [1.0, 0.0, 0.0, 0.0]
    saved = await store.add(existing, embedding=embedding_a)
    await store.approve(saved.id)

    class _MockEmbedder:
        async def embed_query(self, _text: str) -> list[float]:
            # Return an embedding almost identical to embedding_a
            return [0.999, 0.001, 0.0, 0.0]

    result = await extractor.extract_from_thread(
        SAMPLE_MESSAGES[:2], embedder=_MockEmbedder()
    )
    assert result.skipped_duplicate >= 1


# ---------------------------------------------------------------------------
# 5. Contradiction / supersede
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contradiction_triggers_supersede(store: SQLiteMemoryStore) -> None:
    """A semantically similar but not identical fact should supersede the old one."""
    from aegismind_core.memory.settings import MemorySettings

    settings = MemorySettings(
        contradiction_similarity_threshold=0.75,
        dedup_similarity_threshold=0.95,  # high dedup so contradiction fires first
    )

    # Store old fact with an embedding
    old = MemoryRecord(
        namespace="global",
        content="The user works 9 AM to 5 PM.",
        type=MemoryType.SEMANTIC,
    )
    emb_old = [1.0, 0.0, 0.0, 0.0]
    saved_old = await store.add(old, embedding=emb_old)
    await store.approve(saved_old.id)

    # New (contradictory) fact with similar but not identical embedding
    new_candidate = {
        "content": "The user now works 10 AM to 7 PM.",
        "type": "semantic",
        "importance": 0.7,
        "confidence": 0.90,
        "entities": [],
    }

    class _MockEmbedder:
        async def embed_query(self, _text: str) -> list[float]:
            # sim = ~0.80 -- within contradiction window [0.75, 0.95)
            return [0.9, 0.3, 0.0, 0.0]

    extractor = MemoryExtractor(
        store=store, llm_fn=_make_llm([new_candidate]), settings=settings
    )
    result = await extractor.extract_from_thread(
        [{"role": "user", "content": "I changed my hours."}],
        embedder=_MockEmbedder(),
    )

    assert len(result.superseded) >= 1, "Expected at least one supersede event"
    assert result.superseded[0]["old_id"] == saved_old.id

    # Old memory should now be SUPERSEDED
    old_after = await store.get(saved_old.id)
    assert old_after is not None
    assert old_after.status == MemoryStatus.SUPERSEDED


# ---------------------------------------------------------------------------
# 6. Bad JSON from LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bad_json_returns_empty(store: SQLiteMemoryStore) -> None:
    """If the LLM returns unparseable output, extract_from_thread must not raise."""

    async def _bad_llm(_prompt: str) -> str:
        return "I could not parse this. Here is some text without JSON."

    extractor = MemoryExtractor(store=store, llm_fn=_bad_llm)
    result = await extractor.extract_from_thread(SAMPLE_MESSAGES)
    assert result.extracted == []


@pytest.mark.asyncio
async def test_partial_json_with_code_fence_parsed(store: SQLiteMemoryStore) -> None:
    """The parser must strip markdown code fences and extract the array."""
    cand = [{"content": "Python is popular.", "type": "semantic",
             "importance": 0.5, "confidence": 0.9, "entities": ["Python"]}]
    raw = f"```json\n{json.dumps(cand)}\n```"

    async def _fenced_llm(_prompt: str) -> str:
        return raw

    extractor = MemoryExtractor(store=store, llm_fn=_fenced_llm)
    result = await extractor.extract_from_thread(SAMPLE_MESSAGES[:2])
    assert len(result.extracted) == 1
    assert "Python" in result.extracted[0].content


@pytest.mark.asyncio
async def test_llm_failure_returns_empty(store: SQLiteMemoryStore) -> None:
    """Network or runtime errors from the LLM must not propagate; return empty."""
    import asyncio

    async def _failing_llm(_prompt: str) -> str:
        raise asyncio.TimeoutError("connection timed out")

    extractor = MemoryExtractor(store=store, llm_fn=_failing_llm)
    result = await extractor.extract_from_thread(SAMPLE_MESSAGES)
    assert result.extracted == []


# ---------------------------------------------------------------------------
# 7. SaveMemoryAdapter with new store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_memory_adapter_creates_pending_record(
    store: SQLiteMemoryStore,
) -> None:
    from aegismind_core.agent.tools import SaveMemoryAdapter

    adapter = SaveMemoryAdapter(store=store)
    result = await adapter.save_memory("The user prefers TypeScript over JavaScript.", ["preferences", "tech"])
    assert "MEMORY_SAVED" in result
    assert "pending" in result.lower()


@pytest.mark.asyncio
@pytest.mark.guardrail
async def test_save_memory_adapter_rejects_secrets(
    store: SQLiteMemoryStore,
) -> None:
    from aegismind_core.agent.tools import SaveMemoryAdapter

    adapter = SaveMemoryAdapter(store=store)
    result = await adapter.save_memory(
        'api_key = "sk-live-thisisasecrettoken1234567890"', ["secret"]
    )
    assert "MEMORY_REJECTED" in result, "Secret fact must be rejected by guard"


# ---------------------------------------------------------------------------
# 8. _format_messages and _parse_candidates unit tests
# ---------------------------------------------------------------------------


def test_format_messages_basic() -> None:
    msgs = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    result = _format_messages(msgs)
    assert "User: Hello" in result
    assert "Assistant: Hi there" in result


def test_format_messages_skips_empty_content() -> None:
    msgs = [{"role": "user", "content": ""}, {"role": "assistant", "content": "Hello"}]
    result = _format_messages(msgs)
    assert "User:" not in result


def test_parse_candidates_valid_array() -> None:
    raw = json.dumps([{"content": "test", "type": "semantic",
                       "importance": 0.5, "confidence": 1.0, "entities": []}])
    result = _parse_candidates(raw)
    assert len(result) == 1
    assert result[0]["content"] == "test"


def test_parse_candidates_with_code_fence() -> None:
    cand = [{"content": "test", "type": "semantic",
             "importance": 0.5, "confidence": 1.0, "entities": []}]
    raw = f"```json\n{json.dumps(cand)}\n```"
    result = _parse_candidates(raw)
    assert len(result) == 1


def test_parse_candidates_with_preamble() -> None:
    cand = [{"content": "fact", "type": "episodic",
             "importance": 0.5, "confidence": 0.8, "entities": []}]
    raw = f"Here are the extracted facts:\n{json.dumps(cand)}\nEnd."
    result = _parse_candidates(raw)
    assert len(result) == 1


def test_parse_candidates_invalid_returns_empty() -> None:
    result = _parse_candidates("Not valid JSON at all.")
    assert result == []


def test_parse_candidates_empty_array() -> None:
    result = _parse_candidates("[]")
    assert result == []
