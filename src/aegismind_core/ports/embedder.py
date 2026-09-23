from __future__ import annotations

from abc import ABC, abstractmethod


class EmbedderPort(ABC):
    """Abstract port for generating dense text vector representations."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding vector for a search query.

        Args:
            text: Query string to encode.

        Returns:
            List of floats representing query embedding vector.
        """
        ...

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of text documents.

        Args:
            texts: List of strings to encode.

        Returns:
            List of float lists representing document embeddings.
        """
        ...
