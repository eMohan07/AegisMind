from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

import httpx

from aegismind_retrieval.ports import (
    EmbedderPort,
    QueryRewriterPort,
    RerankerPort,
    ScoredChunk,
)

logger = logging.getLogger(__name__)


def _deterministic_embedding(text: str, dim: int = 64) -> list[float]:
    """Generate a deterministic unit-normalized float vector based on text hash."""
    vec = [0.0] * dim
    clean = text.lower().strip()
    for word in clean.split():
        h = int(hashlib.md5(word.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
        for i in range(dim):
            vec[i] += ((h >> (i % 32)) & 0xFF) / 255.0 - 0.5
    # Normalize to unit vector
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        return [round(x / norm, 6) for x in vec]
    return [1.0 / math.sqrt(dim)] * dim


class MockEmbedderAdapter(EmbedderPort):
    """Deterministic in-memory embedder for tests and local development."""

    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension

    async def embed_query(self, query: str) -> list[float]:
        return _deterministic_embedding(query, self.dimension)

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return [_deterministic_embedding(doc, self.dimension) for doc in documents]

    async def embed_sparse_query(self, query: str) -> dict[int, float]:
        return _deterministic_sparse_vector(query)

    async def embed_sparse_documents(self, documents: list[str]) -> list[dict[int, float]]:
        return [_deterministic_sparse_vector(doc) for doc in documents]


def _deterministic_sparse_vector(text: str) -> dict[int, float]:
    """Generate deterministic pseudo-lexical sparse token weights."""
    words = [w.strip(".,!?:;\"'()[]{}").lower() for w in text.split() if w.strip()]
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    sparse: dict[int, float] = {}
    for word, count in counts.items():
        token_id = int(hashlib.md5(word.encode("utf-8"), usedforsecurity=False).hexdigest()[:6], 16)
        sparse[token_id] = round(math.log(1.0 + count), 4)
    return sparse


class MockQueryRewriterAdapter:
    """Mock query rewriter resolving conversational references using heuristic context."""

    async def rewrite_query(
        self,
        query: str,
        history: list[Any] | None = None,
    ) -> str:
        clean_q = query.strip()
        if not history:
            return clean_q

        # Extract last user topic or entity from history turns
        last_context = ""
        for turn in reversed(history):
            content = (
                getattr(turn, "content", "")
                if not isinstance(turn, dict)
                else turn.get("content", "")
            )
            if content and content != clean_q:
                last_context = content
                break

        if not last_context:
            return clean_q

        lower_q = clean_q.lower()
        pronoun_triggers = [
            "it",
            "this",
            "that",
            "the one",
            "the eu one",
            "what about",
            "how about",
        ]
        if any(trigger in lower_q for trigger in pronoun_triggers):
            # Formulate self-contained resolved query
            return f"{clean_q} regarding {last_context[:60]}"

        return clean_q


class OllamaQueryRewriterAdapter:
    """Ollama query rewriter resolving pronouns and conversational follow-ups."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "llama3.2:latest",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client
        self._fallback = MockQueryRewriterAdapter()

    async def rewrite_query(
        self,
        query: str,
        history: list[Any] | None = None,
    ) -> str:
        if not history:
            return query.strip()

        history_lines = []
        for turn in history[-4:]:
            role = (
                getattr(turn, "role", "user")
                if not isinstance(turn, dict)
                else turn.get("role", "user")
            )
            content = (
                getattr(turn, "content", "")
                if not isinstance(turn, dict)
                else turn.get("content", "")
            )
            history_lines.append(f"{role.capitalize()}: {content}")
        history_text = "\n".join(history_lines)

        prompt = (
            "You are a search query rewriting specialist.\n"
            "Given the following conversation history and follow-up question, rewrite "
            "the follow-up question into a standalone, fully-resolved enterprise search "
            "query with all pronouns resolved.\n"
            "Output ONLY the rewritten query, nothing else.\n\n"
            f"Conversation History:\n{history_text}\n\n"
            f"Follow-up Question: {query}\n"
            "Standalone Query:"
        )

        if self._client is not None:
            try:
                resp = await self._client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                    },
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    val = data.get("response", "") if isinstance(data, dict) else ""
                    rewritten = str(val).strip()
                    if rewritten:
                        return rewritten
            except Exception as exc:
                logger.debug("Ollama query rewrite call failed: %s", exc)

        return await self._fallback.rewrite_query(query, history)


class LLMQueryRewriterAdapter:
    """Query rewriter utilizing any provider conforming to LLMPort."""

    def __init__(
        self,
        llm: Any,
        fallback: QueryRewriterPort | None = None,
    ) -> None:
        self.llm = llm
        self._fallback = fallback or MockQueryRewriterAdapter()

    async def rewrite_query(
        self,
        query: str,
        history: list[Any] | None = None,
    ) -> str:
        if not history:
            return query.strip()

        history_lines = []
        for turn in history[-4:]:
            role = (
                getattr(turn, "role", "user")
                if not isinstance(turn, dict)
                else turn.get("role", "user")
            )
            content = (
                getattr(turn, "content", "")
                if not isinstance(turn, dict)
                else turn.get("content", "")
            )
            history_lines.append(f"{role.capitalize()}: {content}")
        history_text = "\n".join(history_lines)

        prompt = (
            "You are a search query rewriting specialist.\n"
            "Given the following conversation history and follow-up question, rewrite "
            "the follow-up question into a standalone, fully-resolved enterprise search "
            "query with all pronouns resolved.\n"
            "Output ONLY the rewritten query, nothing else.\n\n"
            f"Conversation History:\n{history_text}\n\n"
            f"Follow-up Question: {query}\n"
            "Standalone Query:"
        )

        try:
            res = await self.llm.generate(prompt=prompt)
            rewritten = str(res).strip()
            if rewritten:
                return rewritten
        except Exception as exc:
            logger.debug("LLM query rewrite call failed: %s", exc)

        fallback_res = await self._fallback.rewrite_query(query, history)
        return str(fallback_res)


class MockRerankerAdapter(RerankerPort):
    """Deterministic in-memory reranker scoring candidates based on term overlap."""

    async def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_n: int,
    ) -> list[ScoredChunk]:
        query_terms = set(query.lower().split())
        scored: list[ScoredChunk] = []

        for item in candidates:
            chunk_terms = set(item.chunk.content.lower().split())
            overlap = len(query_terms & chunk_terms)
            overlap_score = overlap / max(1, len(query_terms))
            # Combine original retrieval score with term overlap
            combined = round(0.4 * item.score + 0.6 * overlap_score, 4)
            scored.append(ScoredChunk(chunk=item.chunk, score=combined))

        scored.sort(key=lambda sc: sc.score, reverse=True)
        return scored[:top_n]


class TeiEmbedderAdapter(EmbedderPort):
    """Text Embeddings Inference (TEI) client adapter targeting BAAI/bge-m3."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        model: str = "BAAI/bge-m3",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client
        self._fallback = MockEmbedderAdapter(dimension=1024)

    async def embed_query(self, query: str) -> list[float]:
        embeddings = await self.embed_documents([query])
        return embeddings[0]

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if self._client is not None:
            try:
                resp = await self._client.post(
                    f"{self.base_url}/embed",
                    json={"inputs": documents},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data
            except Exception as exc:
                logger.warning("TEI embed call failed, falling back to mock: %s", exc)

        return await self._fallback.embed_documents(documents)

    async def embed_sparse_query(self, query: str) -> dict[int, float]:
        res = await self.embed_sparse_documents([query])
        return res[0]

    async def embed_sparse_documents(self, documents: list[str]) -> list[dict[int, float]]:
        if self._client is not None:
            try:
                resp = await self._client.post(
                    f"{self.base_url}/embed_sparse",
                    json={"inputs": documents},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return [{int(k): float(v) for k, v in item.items()} for item in data]
            except Exception as exc:
                logger.debug("TEI sparse embed failed, falling back to lexical: %s", exc)
        return await self._fallback.embed_sparse_documents(documents)


class TeiRerankerAdapter(RerankerPort):
    """Text Embeddings Inference (TEI) client adapter targeting BAAI/bge-reranker-v2-m3."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8081",
        model: str = "BAAI/bge-reranker-v2-m3",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client
        self._fallback = MockRerankerAdapter()

    async def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_n: int,
    ) -> list[ScoredChunk]:
        if not candidates:
            return []

        if self._client is not None:
            texts = [c.chunk.content for c in candidates]
            try:
                resp = await self._client.post(
                    f"{self.base_url}/rerank",
                    json={"query": query, "texts": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                # TEI returns [{"index": 0, "score": 0.95}, ...]
                scored: list[ScoredChunk] = []
                for item in data:
                    idx = item.get("index", 0)
                    score = float(item.get("score", 0.0))
                    if 0 <= idx < len(candidates):
                        scored.append(ScoredChunk(chunk=candidates[idx].chunk, score=score))
                scored.sort(key=lambda sc: sc.score, reverse=True)
                return scored[:top_n]
            except Exception as exc:
                logger.warning("TEI rerank call failed, falling back to mock: %s", exc)

        return await self._fallback.rerank(query, candidates, top_n)
