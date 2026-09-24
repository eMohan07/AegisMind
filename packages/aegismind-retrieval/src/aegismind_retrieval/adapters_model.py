from __future__ import annotations

import hashlib
import logging
import math

import httpx

from aegismind_retrieval.ports import EmbedderPort, RerankerPort, ScoredChunk

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
