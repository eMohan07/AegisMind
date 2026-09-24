from __future__ import annotations

import logging
import math
from typing import Any

from aegismind_authz.mappers import encode_subject
from aegismind_authz.ports import AuthzPort, CheckRequest
from aegismind_types import Citation, Principal, SearchResult, TokenConsistency
from pydantic import BaseModel, ConfigDict, Field

from aegismind_retrieval.ports import EmbedderPort, RerankerPort, VectorStorePort

logger = logging.getLogger(__name__)


class PipelineResult(BaseModel):
    """Result returned by the Sacred Enforcement Pipeline."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., description="Query string executed")
    results: list[SearchResult] = Field(
        default_factory=list,
        description="Top reranked search results with attached citations",
    )
    total_candidates_evaluated: int = Field(
        ...,
        description="Total overfetched candidate chunks evaluated prior to authz check",
    )
    authorized_candidates_count: int = Field(
        ...,
        description="Count of candidate chunks surviving the bulk authz check",
    )
    overfetch_factor: float = Field(
        ...,
        description="Effective overfetch multiplier applied",
    )


class RetrievalPipeline:
    """The Sacred Enforcement Pipeline for permission-guarded hybrid retrieval.

    Enforces the mandatory 7-stage retrieval lifecycle:
    1. Embed query.
    2. Vector search with coarse tenant & group pre-filter.
    3. Overfetch by factor of 3 to 5.
    4. Call authz.bulk_check with consistency at_least_as_fresh.
    5. Keep strictly allowed documents (drop denied candidates).
    6. Rerank allowed candidates.
    7. Attach deep-linked citations.
    """

    def __init__(
        self,
        authz: AuthzPort,
        vector_store: VectorStorePort,
        embedder: EmbedderPort,
        reranker: RerankerPort,
    ) -> None:
        self.authz = authz
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker

    async def execute(
        self,
        query: str,
        principal: Principal,
        sparse_query: dict[int, float] | None = None,
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
        overfetch_factor: float = 4.0,
        consistency: TokenConsistency | None = None,
    ) -> PipelineResult:
        """Execute the Sacred Enforcement Pipeline."""
        logger.info(
            "Executing Sacred Enforcement Pipeline: user='%s', query='%s', top_k=%d",
            principal.id,
            query,
            top_k,
        )

        # Stage 1: Embed query
        query_vector = await self.embedder.embed_query(query)

        # Stage 2: Prepare coarse tenant and group pre-filter
        coarse_filter = dict(pre_filter or {})
        if principal.tenant_id and "tenant_id" not in coarse_filter:
            coarse_filter["tenant_id"] = principal.tenant_id
        if "groups" not in coarse_filter and "groups" in principal.attributes:
            coarse_filter["groups"] = principal.attributes["groups"]

        # Stage 3: Overfetch by factor of 3 to 5
        clamped_overfetch = max(3.0, min(5.0, float(overfetch_factor)))
        candidates_to_fetch = int(math.ceil(top_k * clamped_overfetch))

        candidates = await self.vector_store.query(
            vector=query_vector,
            sparse_vector=sparse_query,
            pre_filter=coarse_filter,
            top_k=candidates_to_fetch,
        )
        total_evaluated = len(candidates)
        logger.debug(
            "Overfetched %d candidates (target=%d, factor=%.1f)",
            total_evaluated,
            candidates_to_fetch,
            clamped_overfetch,
        )

        if not candidates:
            return PipelineResult(
                query=query,
                results=[],
                total_candidates_evaluated=0,
                authorized_candidates_count=0,
                overfetch_factor=clamped_overfetch,
            )

        # Stage 4: Call authz.bulk_check with consistency at_least_as_fresh
        subject_str = encode_subject(principal)
        unique_doc_ids = list(dict.fromkeys(c.chunk.document_id for c in candidates))

        check_requests = [
            CheckRequest(
                resource=f"document:{doc_id}",
                permission="viewer",
                subject=subject_str,
            )
            for doc_id in unique_doc_ids
        ]

        # Enforce at_least_as_fresh consistency
        enforced_consistency = TokenConsistency(
            requirement="at_least_as_fresh",
            token=consistency.token if consistency else None,
        )

        decisions = await self.authz.bulk_check(
            requests=check_requests,
            consistency=enforced_consistency,
        )

        # Stage 5: Keep strictly allowed documents (drop denied candidates)
        allowed_doc_ids = {
            doc_id
            for doc_id, is_allowed in zip(unique_doc_ids, decisions, strict=False)
            if is_allowed
        }

        allowed_candidates = [
            candidate for candidate in candidates if candidate.chunk.document_id in allowed_doc_ids
        ]
        authorized_count = len(allowed_candidates)
        logger.debug(
            "Authorization retained %d of %d candidates for '%s'",
            authorized_count,
            total_evaluated,
            principal.id,
        )

        if not allowed_candidates:
            return PipelineResult(
                query=query,
                results=[],
                total_candidates_evaluated=total_evaluated,
                authorized_candidates_count=0,
                overfetch_factor=clamped_overfetch,
            )

        # Stage 6: Rerank allowed candidates
        reranked = await self.reranker.rerank(
            query=query,
            candidates=allowed_candidates,
            top_n=top_k,
        )

        # Stage 7: Attach deep-linked citations
        results: list[SearchResult] = []
        for item in reranked:
            chunk = item.chunk
            doc_title = str(chunk.metadata.get("title", f"Document {chunk.document_id}"))
            chunk_uri = chunk.metadata.get("uri") or f"doc://{chunk.document_id}#chunk={chunk.id}"

            snippet = chunk.content[:200] + ("..." if len(chunk.content) > 200 else "")
            citation = Citation(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=doc_title,
                uri=chunk_uri,
                snippet=snippet,
                score=round(item.score, 4),
            )

            results.append(
                SearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    title=doc_title,
                    uri=chunk_uri,
                    text=chunk.content,
                    score=round(item.score, 4),
                    citation=citation,
                )
            )

        return PipelineResult(
            query=query,
            results=results,
            total_candidates_evaluated=total_evaluated,
            authorized_candidates_count=authorized_count,
            overfetch_factor=clamped_overfetch,
        )
