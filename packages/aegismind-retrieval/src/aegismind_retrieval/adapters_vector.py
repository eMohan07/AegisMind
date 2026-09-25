from __future__ import annotations

import logging
import math
from typing import Any

import httpx
from aegismind_types import Chunk

from aegismind_retrieval.ports import ScoredChunk, VectorStorePort
from aegismind_retrieval.rrf import fuse_dense_sparse

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _sparse_dot_product(a: dict[int, float], b: dict[int, float]) -> float:
    """Compute dot product between two sparse index-weight vectors."""
    if len(a) > len(b):
        a, b = b, a
    return sum(weight * b[idx] for idx, weight in a.items() if idx in b)


class MemoryVectorStoreAdapter(VectorStorePort):
    """In-memory hybrid vector store supporting dense, sparse, and RRF search."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}

    async def upsert(self, chunks: list[Chunk]) -> None:
        """Insert or update chunks in memory."""
        for c in chunks:
            self._chunks[c.id] = c
        logger.debug("Upserted %d chunks into memory vector store", len(chunks))

    def _matches_filter(self, chunk: Chunk, pre_filter: dict[str, Any] | None) -> bool:
        if not pre_filter:
            return True

        # 1. Tenant boundary filtering
        expected_tenant = pre_filter.get("tenant_id") or pre_filter.get("tenant")
        if expected_tenant is not None:
            chunk_tenant = chunk.metadata.get("tenant_id") or chunk.metadata.get("tenant")
            if chunk_tenant is not None and str(chunk_tenant) != str(expected_tenant):
                return False

        # 2. Coarse group pre-filtering
        allowed_groups = pre_filter.get("allowed_groups") or pre_filter.get("groups")
        if allowed_groups is not None:
            group_set = {str(g) for g in allowed_groups}
            chunk_groups = set(chunk.metadata.get("groups", []))
            for p in chunk.acl.allowed_principals:
                if p.startswith("group:"):
                    chunk_groups.add(p[len("group:") :])
                else:
                    chunk_groups.add(p)
            # If chunk specifies group restrictions, verify caller has at least one
            if chunk_groups and not (group_set & chunk_groups):
                return False

        # 3. Arbitrary metadata matching
        for k, v in pre_filter.items():
            if k in {"tenant_id", "tenant", "allowed_groups", "groups"}:
                continue
            if chunk.metadata.get(k) != v:
                return False

        return True

    async def query_dense(
        self,
        vector: list[float],
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Perform dense vector search with tenant and group pre-filtering."""
        filtered = [c for c in self._chunks.values() if self._matches_filter(c, pre_filter)]
        dense_results: list[ScoredChunk] = []
        for chunk in filtered:
            if chunk.embedding:
                score = _cosine_similarity(vector, chunk.embedding)
                dense_results.append(ScoredChunk(chunk=chunk, score=score))
        dense_results.sort(key=lambda sc: sc.score, reverse=True)
        return dense_results[:top_k]

    async def query_lexical(
        self,
        query_text: str,
        sparse_vector: dict[int, float] | None = None,
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Perform lexical BM25 / token matching search with tenant and group pre-filtering."""
        filtered = [c for c in self._chunks.values() if self._matches_filter(c, pre_filter)]
        results: list[ScoredChunk] = []
        query_tokens = set(query_text.lower().split())

        for chunk in filtered:
            score = 0.0
            if sparse_vector and chunk.sparse_embedding:
                score = _sparse_dot_product(sparse_vector, chunk.sparse_embedding)
            elif query_tokens:
                chunk_tokens = set(chunk.content.lower().split())
                overlap = len(query_tokens & chunk_tokens)
                score = overlap / max(1, len(query_tokens))

            if score > 0.0:
                results.append(ScoredChunk(chunk=chunk, score=score))

        results.sort(key=lambda sc: sc.score, reverse=True)
        return results[:top_k]

    async def query(
        self,
        vector: list[float] | None = None,
        sparse_vector: dict[int, float] | None = None,
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Perform hybrid or single-vector search with coarse pre-filtering."""
        filtered = [c for c in self._chunks.values() if self._matches_filter(c, pre_filter)]

        if not filtered:
            return []

        # 1. Dense search ranking
        dense_results: list[ScoredChunk] = []
        if vector is not None:
            for chunk in filtered:
                if chunk.embedding:
                    score = _cosine_similarity(vector, chunk.embedding)
                    dense_results.append(ScoredChunk(chunk=chunk, score=score))
            dense_results.sort(key=lambda sc: sc.score, reverse=True)

        # 2. Sparse search ranking
        sparse_results: list[ScoredChunk] = []
        if sparse_vector is not None:
            for chunk in filtered:
                if chunk.sparse_embedding:
                    score = _sparse_dot_product(sparse_vector, chunk.sparse_embedding)
                    sparse_results.append(ScoredChunk(chunk=chunk, score=score))
            sparse_results.sort(key=lambda sc: sc.score, reverse=True)

        # 3. Combine or return
        if vector is not None and sparse_vector is not None:
            fused = fuse_dense_sparse(dense_results, sparse_results)
            return fused[:top_k]

        if vector is not None:
            return dense_results[:top_k]

        if sparse_vector is not None:
            return sparse_results[:top_k]

        # Fallback if neither provided: return initial items with default score
        return [ScoredChunk(chunk=c, score=1.0) for c in filtered[:top_k]]

    async def delete(self, chunk_ids: list[str]) -> bool:
        """Delete chunks by ID."""
        deleted = False
        for cid in chunk_ids:
            if self._chunks.pop(cid, None) is not None:
                deleted = True
        return deleted


class PgVectorScaleAdapter(VectorStorePort):
    """PostgreSQL pgvectorscale adapter supporting StreamingDiskANN and HNSW indexes."""

    def __init__(
        self,
        db_pool: Any | None = None,
        table_name: str = "aegismind_chunks",
    ) -> None:
        self.db_pool = db_pool
        self.table_name = table_name
        self._fallback = MemoryVectorStoreAdapter()

    async def upsert(self, chunks: list[Chunk]) -> None:
        """Insert or update chunks in pgvectorscale table."""
        if self.db_pool is not None:
            # When db pool attached, execute batch SQL insert
            async with self.db_pool.acquire() as conn:
                for c in chunks:
                    query = (
                        f"INSERT INTO {self.table_name} (id, document_id, content, "  # noqa: S608
                        f"embedding, metadata) VALUES ($1, $2, $3, $4, $5) "
                        f"ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, "
                        f"embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata"
                    )
                    await conn.execute(
                        query, c.id, c.document_id, c.content, c.embedding, c.metadata
                    )
            return
        await self._fallback.upsert(chunks)

    async def query_dense(
        self,
        vector: list[float],
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Query pgvectorscale with DiskANN index and cosine distance."""
        if self.db_pool is not None:
            tenant_id = pre_filter.get("tenant_id") if pre_filter else None
            if tenant_id:
                query = (
                    f"SELECT id, document_id, content, metadata, "  # noqa: S608
                    f"1 - (dense_embedding <=> $1::vector) AS score FROM {self.table_name} "
                    f"WHERE tenant_id = $2 "
                    f"ORDER BY dense_embedding <=> $1::vector LIMIT $3"
                )
                async with self.db_pool.acquire() as conn:
                    rows = await conn.fetch(query, vector, tenant_id, top_k)
            else:
                query = (
                    f"SELECT id, document_id, content, metadata, "  # noqa: S608
                    f"1 - (dense_embedding <=> $1::vector) AS score FROM {self.table_name} "
                    f"ORDER BY dense_embedding <=> $1::vector LIMIT $2"
                )
                async with self.db_pool.acquire() as conn:
                    rows = await conn.fetch(query, vector, top_k)

            return [
                ScoredChunk(
                    chunk=Chunk(
                        id=r["id"],
                        document_id=r["document_id"],
                        content=r["content"],
                        metadata=r.get("metadata", {}),
                    ),
                    score=float(r["score"]),
                )
                for r in rows
            ]
        return await self._fallback.query_dense(vector, pre_filter, top_k)

    async def query_lexical(
        self,
        query_text: str,
        sparse_vector: dict[int, float] | None = None,
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Query PostgreSQL full-text search with tenant scoping."""
        if self.db_pool is not None:
            tenant_id = pre_filter.get("tenant_id") if pre_filter else None
            if tenant_id:
                query = (
                    f"SELECT id, document_id, content, metadata, "  # noqa: S608
                    f"ts_rank_cd(to_tsvector('english', content), "
                    f"plainto_tsquery('english', $1)) AS score "
                    f"FROM {self.table_name} "
                    f"WHERE tenant_id = $2 AND "
                    f"to_tsvector('english', content) @@ plainto_tsquery('english', $1) "
                    f"ORDER BY score DESC LIMIT $3"
                )
                async with self.db_pool.acquire() as conn:
                    rows = await conn.fetch(query, query_text, tenant_id, top_k)
            else:
                query = (
                    f"SELECT id, document_id, content, metadata, "  # noqa: S608
                    f"ts_rank_cd(to_tsvector('english', content), "
                    f"plainto_tsquery('english', $1)) AS score "
                    f"FROM {self.table_name} "
                    f"WHERE to_tsvector('english', content) @@ "
                    f"plainto_tsquery('english', $1) "
                    f"ORDER BY score DESC LIMIT $2"
                )
                async with self.db_pool.acquire() as conn:
                    rows = await conn.fetch(query, query_text, top_k)

            return [
                ScoredChunk(
                    chunk=Chunk(
                        id=r["id"],
                        document_id=r["document_id"],
                        content=r["content"],
                        metadata=r.get("metadata", {}),
                    ),
                    score=float(r["score"]),
                )
                for r in rows
            ]
        return await self._fallback.query_lexical(query_text, sparse_vector, pre_filter, top_k)

    async def query(
        self,
        vector: list[float] | None = None,
        sparse_vector: dict[int, float] | None = None,
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Query pgvectorscale with DiskANN index and cosine distance."""
        if vector is not None:
            return await self.query_dense(vector, pre_filter, top_k)
        return await self._fallback.query(vector, sparse_vector, pre_filter, top_k)

    async def delete(self, chunk_ids: list[str]) -> bool:
        """Delete chunks from pgvectorscale."""
        if self.db_pool is not None:
            query = f"DELETE FROM {self.table_name} WHERE id = ANY($1)"  # noqa: S608
            async with self.db_pool.acquire() as conn:
                res = await conn.execute(query, chunk_ids)
                return "DELETE" in res
        return await self._fallback.delete(chunk_ids)


class QdrantVectorStoreAdapter(VectorStorePort):
    """Qdrant REST adapter supporting dense vectors, sparse vectors, and payload filtering."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:6333",
        collection_name: str = "aegismind_chunks",
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.collection_name = collection_name
        self.api_key = api_key
        self._client = client
        self._fallback = MemoryVectorStoreAdapter()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers

    async def upsert(self, chunks: list[Chunk]) -> None:
        """Upsert points into Qdrant collection."""
        await self._fallback.upsert(chunks)
        if self._client is not None:
            points = [
                {
                    "id": c.id,
                    "vector": c.embedding or [],
                    "payload": {
                        "document_id": c.document_id,
                        "content": c.content,
                        "metadata": c.metadata,
                    },
                }
                for c in chunks
            ]
            endpoint = f"{self.url}/collections/{self.collection_name}/points"
            await self._client.put(endpoint, json={"points": points}, headers=self._headers())

    async def query(
        self,
        vector: list[float] | None = None,
        sparse_vector: dict[int, float] | None = None,
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Search points in Qdrant collection."""
        if self._client is not None and vector is not None:
            endpoint = f"{self.url}/collections/{self.collection_name}/points/search"
            payload: dict[str, Any] = {
                "vector": vector,
                "limit": top_k,
                "with_payload": True,
            }
            if pre_filter:
                conditions = []
                for k, v in pre_filter.items():
                    conditions.append({"key": f"metadata.{k}", "match": {"value": v}})
                payload["filter"] = {"must": conditions}

            try:
                resp = await self._client.post(endpoint, json=payload, headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json().get("result", [])
                    return [
                        ScoredChunk(
                            chunk=Chunk(
                                id=str(item["id"]),
                                document_id=item.get("payload", {}).get("document_id", ""),
                                content=item.get("payload", {}).get("content", ""),
                                metadata=item.get("payload", {}).get("metadata", {}),
                            ),
                            score=float(item.get("score", 0.0)),
                        )
                        for item in data
                    ]
            except Exception as exc:
                logger.warning("Qdrant remote search failed, using fallback: %s", exc)

        return await self._fallback.query(vector, sparse_vector, pre_filter, top_k)

    async def delete(self, chunk_ids: list[str]) -> bool:
        """Delete points from Qdrant."""
        await self._fallback.delete(chunk_ids)
        if self._client is not None:
            endpoint = f"{self.url}/collections/{self.collection_name}/points/delete"
            resp = await self._client.post(
                endpoint, json={"points": chunk_ids}, headers=self._headers()
            )
            return resp.status_code == 200
        return True
