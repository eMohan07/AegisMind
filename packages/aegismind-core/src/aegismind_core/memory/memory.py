from __future__ import annotations

import json
import logging
from typing import Any

from aegismind_core.memory.retriever import MemoryRetriever
from aegismind_core.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Long-term memory for the sovereign agent. Stores all Q&A pairs."""

    def __init__(self, db_path: str = "./storage/memory/memory.db") -> None:
        self.store = MemoryStore(db_path=db_path)
        self.retriever = MemoryRetriever(self.store)

    async def record_conversation(
        self, user_id: str, tenant_id: str, query: str, response: str, embedder: Any | None = None
    ) -> None:
        query_embedding = None
        if embedder:
            try:
                embedding = await embedder.embed_query(query)
                query_embedding = json.dumps(embedding)
            except Exception as exc:
                logger.debug("Failed to compute embedding for conversation turn: %s", exc)
        self.store.store(
            user_id=user_id,
            tenant_id=tenant_id,
            query=query,
            response=response,
            query_embedding=query_embedding,
        )

    async def store_conversation(
        self, user_id: str, tenant_id: str, query: str, response: str, embedder: Any | None = None
    ) -> str:
        """Store a conversation turn and return the ID."""
        query_embedding = None
        if embedder:
            try:
                embedding = await embedder.embed_query(query)
                query_embedding = json.dumps(embedding)
            except Exception:
                pass
        return self.store.store(
            user_id=user_id,
            tenant_id=tenant_id,
            query=query,
            response=response,
            query_embedding=query_embedding,
        )

    async def retrieve_context(
        self, query: str, user_id: str, tenant_id: str, embedder: Any, top_k: int = 5
    ) -> str:
        return await self.retriever.retrieve(query, user_id, tenant_id, embedder, top_k)

    def get_history(self, user_id: str, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return self.retriever.get_history(user_id, tenant_id, limit)

    def get_stats(self, user_id: str, tenant_id: str) -> dict[str, int]:
        return self.retriever.get_stats(user_id, tenant_id)

    def clear(self, user_id: str, tenant_id: str) -> None:
        self.retriever.clear(user_id, tenant_id)


async def retrieve_context_v2(
    store: Any,  # SQLiteMemoryStore
    query: str,
    namespace: str,
    embedder: Any | None = None,
    top_k: int = 5,
) -> tuple[str, list[dict[str, Any]]]:
    """Retrieve memories for a query and format them into an XML-tagged context string.

    Returns:
        A tuple of (formatted_context_string, list_of_memories_used).
        If no memories match, returns ("", []).
    """
    embedding = None
    if embedder is not None:
        try:
            embedding = list(await embedder.embed_query(query))
        except Exception as exc:
            logger.debug("Failed to embed query for memory search: %s", exc)

    results = await store.search(
        query=query,
        embedding=embedding,
        namespace=namespace,
        top_k=top_k,
    )

    if not results:
        return "", []

    memories_used = []
    lines = ["<memory>"]
    for i, res in enumerate(results, start=1):
        mem = res.memory
        lines.append(f"  <fact id=\"{mem.id}\" type=\"{mem.type.value}\">")
        lines.append(f"    {mem.content}")
        lines.append("  </fact>")
        memories_used.append(mem.model_dump())
    
    lines.append("</memory>\n")
    return "\n".join(lines), memories_used
