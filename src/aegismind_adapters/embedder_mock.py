from __future__ import annotations

import hashlib
import logging

from aegismind_core.ports.embedder import EmbedderPort

logger = logging.getLogger(__name__)


class MockEmbedderAdapter(EmbedderPort):
    """Deterministic mock embedder producing normalized pseudo-embeddings."""

    def __init__(self, dimension: int = 16) -> None:
        self.dimension = dimension
        logger.debug("Initialized MockEmbedderAdapter with dimension=%d", dimension)

    def _generate_vector(self, text: str) -> list[float]:
        # Hash text to seed deterministic float values
        tokens = text.lower().split()
        vector = [0.0] * self.dimension

        for i, token in enumerate(tokens):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            val = (digest[0] / 255.0) * 2.0 - 1.0
            idx = (i + digest[1]) % self.dimension
            vector[idx] += val

        # Normalize
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0.0:
            return [v / norm for v in vector]
        return [1.0 / (self.dimension**0.5)] * self.dimension

    async def embed_query(self, text: str) -> list[float]:
        return self._generate_vector(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]
