from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aegismind_retrieval.ports import ScoredChunk
from aegismind_types import SearchResult

from aegismind_core.ollama import build_isolated_prompt
from aegismind_core.ports.llm import LLMPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BudgetedContextResult[T]:
    """Outcome of context budgeting and token constraint enforcement."""

    chunks: list[T]
    original_count: int
    final_count: int
    dropped_count: int
    notice: str | None
    prompt: str
    system_prompt: str
    total_tokens: int


def _extract_chunk_payload(item: Any) -> dict[str, Any]:
    """Normalize SearchResult, ScoredChunk, or custom object to dictionary payload."""
    if isinstance(item, SearchResult):
        return {
            "id": item.chunk_id,
            "document_id": item.document_id,
            "title": item.title,
            "text": item.text,
            "uri": item.uri or "",
            "score": item.score,
            "tenant_id": item.tenant_id or "corp-default",
        }
    if isinstance(item, ScoredChunk):
        return {
            "id": item.chunk.id,
            "document_id": item.chunk.document_id,
            "title": item.chunk.metadata.get("title") or item.chunk.document_id,
            "text": item.chunk.content,
            "uri": item.chunk.metadata.get("uri") or "",
            "score": item.score,
            "tenant_id": item.chunk.metadata.get("tenant_id", "corp-default"),
        }
    return {
        "id": getattr(item, "chunk_id", getattr(item, "id", "")),
        "document_id": getattr(item, "document_id", ""),
        "title": getattr(item, "title", ""),
        "text": getattr(item, "text", getattr(item, "content", "")),
        "uri": getattr(item, "uri", ""),
        "score": getattr(item, "score", 0.0),
        "tenant_id": getattr(item, "tenant_id", "corp-default"),
    }


def apply_context_budget[T](
    query: str,
    results: list[T],
    llm: LLMPort,
    model: str | None = None,
    reserve_output_tokens: int = 1024,
    max_context_override: int | None = None,
) -> BudgetedContextResult[T]:
    """Enforce model context window budget by pruning lowest-scoring chunks atomically.

    Never truncates individual chunks: chunks are atomic units.
    Drops candidates from the bottom (lowest rerank score) until the prompt fits.
    If chunks are dropped, appends:
      'Note: Results trimmed from K to N due to context constraints.'
    """
    total_window = max_context_override or llm.get_context_window(model)
    usable_budget = max(256, total_window - reserve_output_tokens)

    original_count = len(results)
    if not results:
        prompt, system_prompt = build_isolated_prompt(query, [])
        return BudgetedContextResult(
            chunks=[],
            original_count=0,
            final_count=0,
            dropped_count=0,
            notice=None,
            prompt=prompt,
            system_prompt=system_prompt,
            total_tokens=llm.count_tokens(f"{system_prompt}\n{prompt}"),
        )

    # Active chunks ordered by descending rerank score
    active_chunks = list(results)

    while active_chunks:
        doc_payloads = [_extract_chunk_payload(c) for c in active_chunks]
        prompt, system_prompt = build_isolated_prompt(query, doc_payloads)
        full_text = f"{system_prompt}\n{prompt}"
        token_count = llm.count_tokens(full_text, model=model)

        if token_count <= usable_budget:
            dropped = original_count - len(active_chunks)
            notice = (
                f"Note: Results trimmed from {original_count} to {len(active_chunks)} "
                f"due to context constraints."
                if dropped > 0
                else None
            )
            return BudgetedContextResult(
                chunks=active_chunks,
                original_count=original_count,
                final_count=len(active_chunks),
                dropped_count=dropped,
                notice=notice,
                prompt=prompt,
                system_prompt=system_prompt,
                total_tokens=token_count,
            )

        # Drop the chunk with the lowest rerank score (bottom of sorted list)
        dropped_chunk = active_chunks.pop()
        dropped_payload = _extract_chunk_payload(dropped_chunk)
        logger.info(
            "Context budget exceeded (%d > %d tokens). Dropped chunk: %s (score=%.4f)",
            token_count,
            usable_budget,
            dropped_payload.get("id"),
            dropped_payload.get("score", 0.0),
        )

    # If no chunk fits within context window, return empty active chunk set
    prompt, system_prompt = build_isolated_prompt(query, [])
    full_text = f"{system_prompt}\n{prompt}"
    token_count = llm.count_tokens(full_text, model=model)
    notice = (
        f"Note: Results trimmed from {original_count} to 0 due to context constraints."
        if original_count > 0
        else None
    )
    return BudgetedContextResult(
        chunks=[],
        original_count=original_count,
        final_count=0,
        dropped_count=original_count,
        notice=notice,
        prompt=prompt,
        system_prompt=system_prompt,
        total_tokens=token_count,
    )
