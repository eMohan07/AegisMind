from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from aegismind_core.memory.models import (
    MemoryRecord,
    MemoryStatus,
    MemoryType,
)
from aegismind_core.memory.settings import DEFAULT_SETTINGS, MemorySettings
from aegismind_core.memory.sqlite_store import (
    SQLiteMemoryStore,
    _content_hash,
    _cosine,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """\
You are a memory extraction assistant for a sovereign AI agent.
Given a conversation, extract up to {max_candidates} atomic facts worth remembering for future interactions.

Focus on:
- User preferences, habits, and explicitly stated facts
- Decisions made or conclusions reached
- Procedural knowledge (how to do something)
- Named entities and their relationships

Rules:
- Each fact must be ONE concise sentence
- Skip trivial, transient, or purely conversational facts
- Skip any sensitive information (passwords, API keys, credentials)
- Skip meta-commentary about the conversation itself
- Skip facts that are already common knowledge

Return ONLY a valid JSON array (no markdown fences, no commentary).
Each element must have exactly these keys:
  "content"    : string  - the fact, one sentence
  "type"       : string  - one of: semantic | episodic | procedural
  "importance" : number  - 0.0 to 1.0
  "confidence" : number  - 0.0 to 1.0
  "entities"   : array of strings - named entities mentioned

If no facts are worth extracting return an empty array: []

Conversation:
{conversation}

JSON array:"""


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """Summary of one memory extraction run."""

    model_config = ConfigDict(frozen=True)

    extracted: list[MemoryRecord] = Field(default_factory=list)
    skipped_duplicate: int = Field(default=0)
    skipped_contradiction: int = Field(default=0)
    superseded: list[dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_messages(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown").capitalize()
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_candidates(raw: str) -> list[dict[str, Any]]:
    """Extract a JSON array from *raw* LLM output.

    Strips markdown code fences, then tries direct parse, then regex extraction.
    Returns an empty list on any parse failure so callers never crash.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct JSON parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to extract a JSON array substring (greedy - find the largest array)
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("extractor: failed to parse JSON from LLM response (first 200 chars): %s", raw[:200])
    return []


# ---------------------------------------------------------------------------
# MemoryExtractor
# ---------------------------------------------------------------------------


class MemoryExtractor:
    """Extracts typed memory candidates from a conversation thread via an LLM.

    The extraction pipeline:
      1. Format the conversation into a prompt.
      2. Call the LLM (Ollama /api/generate) to get JSON candidates.
      3. Parse and validate each candidate.
      4. Deduplicate (exact hash, then cosine similarity).
      5. Contradiction detection (similar but below dedup threshold -> supersede).
      6. Insert accepted candidates as PENDING MemoryRecords.

    The *llm_fn* parameter accepts an async callable `(prompt: str) -> str`
    that completely replaces the Ollama call. This is used in tests to inject
    deterministic mock responses without starting a real LLM server.
    """

    def __init__(
        self,
        store: SQLiteMemoryStore,
        ollama_url: str = "http://localhost:11434",
        model: str = "llama3.2:latest",
        settings: MemorySettings | None = None,
        llm_fn: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self.store = store
        self._ollama_url = ollama_url.rstrip("/")
        self._model = model
        self.settings = settings or DEFAULT_SETTINGS
        self._llm_fn = llm_fn

    # ------------------------------------------------------------------
    # LLM interface
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM and return the raw response string.

        If *llm_fn* was injected, calls that instead of Ollama.
        All network errors are propagated to the caller so extraction
        can gracefully degrade to returning an empty result.
        """
        if self._llm_fn is not None:
            return await self._llm_fn(prompt)

        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{self._ollama_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return str(resp.json().get("response", ""))

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    async def _is_duplicate(
        self, candidate: MemoryRecord, embedding: list[float] | None
    ) -> bool:
        """Return True if *candidate* is a duplicate of an existing memory."""
        import asyncio

        # 1. Exact content-hash match (any status, same namespace)
        ch = _content_hash(candidate.content)
        existing = await asyncio.to_thread(self.store.find_by_hash, candidate.namespace, ch)
        if existing is not None:
            logger.debug("extractor: dedup by content_hash for namespace=%s", candidate.namespace)
            return True

        # 2. Cosine similarity above the dedup threshold
        if embedding is None:
            return False

        stored_pairs = await asyncio.to_thread(
            self.store.get_active_with_embeddings, candidate.namespace, True
        )
        threshold = self.settings.dedup_similarity_threshold
        for _, stored_emb in stored_pairs:
            if _cosine(embedding, stored_emb) >= threshold:
                logger.debug(
                    "extractor: dedup by cosine >= %.2f for namespace=%s",
                    threshold, candidate.namespace,
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Contradiction detection
    # ------------------------------------------------------------------

    async def _find_contradiction(
        self, candidate: MemoryRecord, embedding: list[float] | None
    ) -> str | None:
        """Return the ID of a contradicting memory if one is found.

        A contradiction is an existing active memory whose embedding similarity
        is >= contradiction_threshold (0.75) but < dedup_threshold (0.90).
        Semantically similar but not identical suggests the candidate updates
        or contradicts the older fact.
        """
        if embedding is None:
            return None

        import asyncio

        stored_pairs = await asyncio.to_thread(
            self.store.get_active_with_embeddings, candidate.namespace, True
        )
        lo = self.settings.contradiction_similarity_threshold
        hi = self.settings.dedup_similarity_threshold

        for record, stored_emb in stored_pairs:
            sim = _cosine(embedding, stored_emb)
            if lo <= sim < hi:
                logger.info(
                    "extractor: contradiction detected sim=%.3f old_id=%s",
                    sim, record.id,
                )
                return record.id

        return None

    # ------------------------------------------------------------------
    # Main extraction
    # ------------------------------------------------------------------

    async def extract_from_thread(
        self,
        messages: list[dict[str, str]],
        namespace: str = "global",
        private: bool = False,
        source_thread_id: str | None = None,
        embedder: Any | None = None,
    ) -> ExtractionResult:
        """Run the full extraction pipeline on a conversation thread.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."} dicts.
            namespace: Memory namespace to write into.
            private: If True, skip extraction entirely (private mode guard).
            source_thread_id: Thread ID to attach to each extracted memory.
            embedder: Optional EmbedderPort for vector dedup and contradiction detection.

        Returns:
            ExtractionResult with lists of extracted, superseded, and skip counts.
        """
        _empty = ExtractionResult()

        if private:
            logger.info("extractor: private thread; skipping extraction")
            return _empty

        if not messages:
            return _empty

        conversation = _format_messages(messages)
        if not conversation.strip():
            return _empty

        prompt = _EXTRACTION_PROMPT.format(
            max_candidates=self.settings.max_extraction_candidates,
            conversation=conversation,
        )

        try:
            raw = await self._call_llm(prompt)
        except Exception as exc:
            logger.warning("extractor: LLM call failed, returning empty result: %s", exc)
            return _empty

        candidates = _parse_candidates(raw)
        candidates = candidates[: self.settings.max_extraction_candidates]

        extracted: list[MemoryRecord] = []
        superseded: list[dict[str, str]] = []
        skipped_dup = 0
        skipped_con = 0

        for raw_cand in candidates:
            content = str(raw_cand.get("content") or "").strip()
            if not content:
                continue

            try:
                mem_type = MemoryType(raw_cand.get("type", "semantic"))
            except ValueError:
                mem_type = MemoryType.SEMANTIC

            importance = max(0.0, min(1.0, float(raw_cand.get("importance", 0.5))))
            confidence = max(0.0, min(1.0, float(raw_cand.get("confidence", 1.0))))
            entities = [str(e) for e in raw_cand.get("entities", []) if e]

            candidate = MemoryRecord(
                namespace=namespace,
                type=mem_type,
                content=content,
                importance=importance,
                confidence=confidence,
                entities_json=entities,
                status=MemoryStatus.PENDING,
                source_thread_id=source_thread_id,
            )

            # Compute embedding if embedder is available
            embedding: list[float] | None = None
            if embedder is not None:
                try:
                    embedding = list(await embedder.embed_query(content))
                except Exception as exc:
                    logger.debug("extractor: embed_query failed: %s", exc)

            # Deduplication check
            try:
                is_dup = await self._is_duplicate(candidate, embedding)
            except Exception as exc:
                logger.debug("extractor: dedup check error: %s", exc)
                is_dup = False

            if is_dup:
                skipped_dup += 1
                continue

            # Contradiction check
            try:
                old_id = await self._find_contradiction(candidate, embedding)
            except Exception as exc:
                logger.debug("extractor: contradiction check error: %s", exc)
                old_id = None

            if old_id is not None:
                try:
                    _, new_saved = await self.store.supersede(
                        old_id, candidate, actor="extractor", embedding=embedding
                    )
                    superseded.append({"old_id": old_id, "new_id": new_saved.id})
                    extracted.append(new_saved)
                    continue
                except Exception as exc:
                    logger.warning(
                        "extractor: supersede old_id=%s failed: %s; counting as skipped",
                        old_id, exc,
                    )
                    skipped_con += 1
                    continue

            # Normal insert
            try:
                saved = await self.store.add(candidate, embedding=embedding)
                extracted.append(saved)
            except ValueError as exc:
                # Secret guard rejection or content error
                logger.info("extractor: memory rejected: %s", exc)
                skipped_dup += 1
            except Exception as exc:
                logger.warning("extractor: store.add failed: %s", exc)

        logger.info(
            "extractor: extracted=%d dup=%d contradiction=%d superseded=%d namespace=%s",
            len(extracted), skipped_dup, skipped_con, len(superseded), namespace,
        )
        return ExtractionResult(
            extracted=extracted,
            skipped_duplicate=skipped_dup,
            skipped_contradiction=skipped_con,
            superseded=superseded,
        )
