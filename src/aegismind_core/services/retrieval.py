from __future__ import annotations

import logging
from typing import Any

from aegismind_core.domain.models import RetrievalQuery, RetrievalResult, ScoredChunk
from aegismind_core.domain.permissions import (
    ConsistencyRequirement,
    ConsistencyToken,
    PermissionCheck,
    Resource,
    Subject,
)
from aegismind_core.ports.authz import AuthzPort
from aegismind_core.ports.embedder import EmbedderPort
from aegismind_core.ports.reranker import RerankerPort
from aegismind_core.ports.vector_store import VectorStorePort
from aegismind_core.registry import resolve_adapter

logger = logging.getLogger(__name__)


class RetrievalService:
    """Core retrieval service enforcing document-level Zanzibar access control.

    The retrieval pipeline executes in stages:
    1. Query embedding generation.
    2. Overfetching candidate chunks from vector storage (3x to 5x top_k).
    3. Bulk authorization check with at_least_as_fresh consistency.
    4. Filtering out unauthorized document candidates.
    5. Reranking allowed candidates to deliver final top_k results.
    """

    def __init__(
        self,
        authz: AuthzPort | None = None,
        vector_store: VectorStorePort | None = None,
        embedder: EmbedderPort | None = None,
        reranker: RerankerPort | None = None,
        authz_adapter_name: str | None = None,
        vector_store_adapter_name: str | None = None,
        embedder_adapter_name: str | None = None,
        reranker_adapter_name: str | None = None,
        adapter_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        kwargs = adapter_kwargs or {}

        # Resolve adapters dynamically via registry if not explicitly injected
        if authz is not None:
            self._authz = authz
        else:
            name = authz_adapter_name or "memory"
            adapter_cls = resolve_adapter("authz", name)
            self._authz = adapter_cls(**kwargs.get("authz", {}))

        if vector_store is not None:
            self._vector_store = vector_store
        else:
            name = vector_store_adapter_name or "memory"
            adapter_cls = resolve_adapter("vector_store", name)
            self._vector_store = adapter_cls(**kwargs.get("vector_store", {}))

        if embedder is not None:
            self._embedder = embedder
        else:
            name = embedder_adapter_name or "mock"
            adapter_cls = resolve_adapter("embedder", name)
            self._embedder = adapter_cls(**kwargs.get("embedder", {}))

        if reranker is not None:
            self._reranker = reranker
        else:
            name = reranker_adapter_name or "mock"
            adapter_cls = resolve_adapter("reranker", name)
            self._reranker = adapter_cls(**kwargs.get("reranker", {}))

        logger.info(
            "Initialized RetrievalService: authz=%s, vector=%s, embedder=%s, reranker=%s",
            type(self._authz).__name__,
            type(self._vector_store).__name__,
            type(self._embedder).__name__,
            type(self._reranker).__name__,
        )

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        """Execute permission-guarded retrieval pipeline.

        Args:
            query: RetrievalQuery containing query text, caller identity, and constraints.

        Returns:
            RetrievalResult containing reranked authorized chunks and evaluation metrics.
        """
        logger.info(
            "Executing retrieval for user '%s', query '%s', top_k=%d",
            query.user_id,
            query.query_text,
            query.top_k,
        )

        # 1. Embed query
        query_vector = await self._embedder.embed_query(query.query_text)

        # 2. Overfetch candidate chunks (bounded between 3.0 and 5.0)
        overfetch_factor = max(3.0, min(5.0, query.overfetch_factor))
        candidates_to_fetch = int(query.top_k * overfetch_factor)

        candidates = await self._vector_store.search(
            query_embedding=query_vector,
            limit=candidates_to_fetch,
            metadata_filter=query.metadata_filter,
        )

        total_evaluated = len(candidates)
        logger.debug(
            "Fetched %d initial candidates (target overfetch=%d)",
            total_evaluated,
            candidates_to_fetch,
        )

        if not candidates:
            return RetrievalResult(
                query_text=query.query_text,
                chunks=[],
                total_candidates_evaluated=0,
                authorized_candidates_count=0,
            )

        # 3. Perform bulk authorization check at at_least_as_fresh consistency
        allowed_candidates = await self._filter_by_permissions(
            candidates=candidates,
            user_id=query.user_id,
            consistency=query.consistency,
        )

        authorized_count = len(allowed_candidates)
        logger.debug(
            "Authorization check retained %d of %d candidates for user '%s'",
            authorized_count,
            total_evaluated,
            query.user_id,
        )

        if not allowed_candidates:
            return RetrievalResult(
                query_text=query.query_text,
                chunks=[],
                total_candidates_evaluated=total_evaluated,
                authorized_candidates_count=0,
            )

        # 4. Rerank allowed candidates to desired top_n
        reranked = await self._reranker.rerank(
            query=query.query_text,
            candidates=allowed_candidates,
            top_n=query.top_k,
        )

        return RetrievalResult(
            query_text=query.query_text,
            chunks=reranked,
            total_candidates_evaluated=total_evaluated,
            authorized_candidates_count=authorized_count,
        )

    async def _filter_by_permissions(
        self,
        candidates: list[ScoredChunk],
        user_id: str,
        consistency: ConsistencyToken,
    ) -> list[ScoredChunk]:
        """Check access permissions for candidate chunks in bulk."""
        subject = Subject(type="user", id=user_id)

        # Deduplicate document IDs for authorization batch check
        unique_doc_ids = list(dict.fromkeys(c.chunk.document_id for c in candidates))

        checks = [
            PermissionCheck(
                subject=subject,
                permission="view",
                resource=Resource(type="document", id=doc_id),
            )
            for doc_id in unique_doc_ids
        ]

        # Ensure at_least_as_fresh consistency requirement
        enforced_consistency = ConsistencyToken(
            requirement=consistency.requirement or ConsistencyRequirement.AT_LEAST_AS_FRESH,
            token=consistency.token,
        )

        decisions = await self._authz.bulk_check(
            checks=checks,
            consistency=enforced_consistency,
        )

        # Map document_id to authorization outcome
        doc_permissions: dict[str, bool] = {}
        for check, decision in zip(checks, decisions, strict=False):
            doc_permissions[check.resource.id] = decision.permitted

        # Retain candidate chunks from allowed documents
        return [
            candidate
            for candidate in candidates
            if doc_permissions.get(candidate.chunk.document_id, False)
        ]
