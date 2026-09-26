from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Any

import httpx

from aegismind_retrieval.ports import EmbedderPort

logger = logging.getLogger(__name__)


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


class LocalDeterministicEmbedderAdapter(EmbedderPort):
    """Zero-cloud deterministic embedder using hash-based vector projection.

    Provides stable vector representations completely offline without requiring any
    external models or services, ideal for sovereign offline testing and local mode fallback.
    """

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def _embed_text(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        words = text.lower().strip().split()
        if not words:
            return [1.0 / math.sqrt(self.dimension)] * self.dimension
        for word in words:
            h = int(hashlib.md5(word.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
            for i in range(self.dimension):
                vec[i] += ((h >> (i % 32)) & 0xFF) / 255.0 - 0.5
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            return [round(x / norm, 6) for x in vec]
        return [1.0 / math.sqrt(self.dimension)] * self.dimension

    async def embed_query(self, query: str) -> list[float]:
        return self._embed_text(query)

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return [self._embed_text(doc) for doc in documents]

    async def embed_sparse_query(self, query: str) -> dict[int, float]:
        return _deterministic_sparse_vector(query)

    async def embed_sparse_documents(self, documents: list[str]) -> list[dict[int, float]]:
        return [_deterministic_sparse_vector(doc) for doc in documents]


class OllamaEmbedderAdapter(EmbedderPort):
    """Local sovereign embedder using Ollama's local embeddings endpoint (e.g. nomic-embed-text).

    Operates completely locally with zero external network egress.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        fallback_embedder: EmbedderPort | None = None,
    ) -> None:
        raw_url = base_url or os.environ.get("OLLAMA_URL") or "http://localhost:11434"
        self.base_url = raw_url.rstrip("/")
        self.model = model or os.environ.get("LOCAL_EMBED_MODEL") or "nomic-embed-text"
        self._fallback = fallback_embedder or LocalDeterministicEmbedderAdapter(dimension=256)

    async def embed_query(self, query: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": query},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    embedding = data.get("embedding")
                    if isinstance(embedding, list) and len(embedding) > 0:
                        return [float(x) for x in embedding]
        except Exception as exc:
            logger.debug("Ollama embed_query failed, falling back to local deterministic: %s", exc)
        return await self._fallback.embed_query(query)

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for doc in documents:
            emb = await self.embed_query(doc)
            results.append(emb)
        return results

    async def embed_sparse_query(self, query: str) -> dict[int, float]:
        return _deterministic_sparse_vector(query)

    async def embed_sparse_documents(self, documents: list[str]) -> list[dict[int, float]]:
        return [_deterministic_sparse_vector(doc) for doc in documents]


class FastEmbedAdapter(EmbedderPort):
    """In-process local sovereign embedder using FastEmbed (ONNX runtime on CPU).

    Falls back to LocalDeterministicEmbedderAdapter if fastembed is not installed.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        fallback_embedder: EmbedderPort | None = None,
    ) -> None:
        self.model_name = model_name
        self._fallback = fallback_embedder or LocalDeterministicEmbedderAdapter(dimension=384)
        self._model: Any = None
        try:
            import importlib

            fastembed_mod = importlib.import_module("fastembed")
            text_embedding_cls = fastembed_mod.TextEmbedding
            self._model = text_embedding_cls(model_name=self.model_name)
            logger.info("FastEmbed local embedder initialized with model: %s", self.model_name)
        except Exception as exc:
            logger.debug("FastEmbed unavailable, using fallback embedder: %s", exc)
            self._model = None

    async def embed_query(self, query: str) -> list[float]:
        if self._model is not None:
            try:
                embeddings = list(self._model.embed([query]))
                if embeddings:
                    return [float(x) for x in embeddings[0]]
            except Exception as exc:
                logger.warning("FastEmbed embed_query error: %s", exc)
        return await self._fallback.embed_query(query)

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if self._model is not None and documents:
            try:
                embeddings = list(self._model.embed(documents))
                return [[float(x) for x in emb] for emb in embeddings]
            except Exception as exc:
                logger.warning("FastEmbed embed_documents error: %s", exc)
        return await self._fallback.embed_documents(documents)

    async def embed_sparse_query(self, query: str) -> dict[int, float]:
        return _deterministic_sparse_vector(query)

    async def embed_sparse_documents(self, documents: list[str]) -> list[dict[int, float]]:
        return [_deterministic_sparse_vector(doc) for doc in documents]
