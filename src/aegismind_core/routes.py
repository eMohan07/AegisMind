from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from aegismind_authz.ports import AuthzPort, RelationshipTuple
from aegismind_connector_sdk.ports import ConnectorPort, ConnectorSpec
from aegismind_infra.ports import SecretStorePort
from aegismind_infra.secrets import MemorySecretStore
from aegismind_ingestion.ports import IngestionPipelinePort
from aegismind_ingestion.worker import ScribeSyncReport, ScribeWorker
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import PipelineResult, RetrievalPipeline
from aegismind_retrieval.ports import VectorStorePort
from aegismind_types import (
    ACL,
    ChatTurn,
    Chunk,
    FeedbackEntry,
    Principal,
)
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from aegismind_core.adapters.llm import get_llm_adapter
from aegismind_core.observability import trace_span
from aegismind_core.ports.llm import LLMPort

logger = logging.getLogger(__name__)


# --- Domain Models for API ---


class FeedbackCreateRequest(BaseModel):
    """Payload for submitting user thumbs up/down feedback."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., description="Query submitted")
    rewritten_query: str | None = Field(default=None, description="Rewritten query string")
    retrieved_chunk_ids: list[str] = Field(default_factory=list, description="IDs of cited chunks")
    rating: Literal["thumbs_up", "thumbs_down"] = Field(..., description="User rating")
    comment: str | None = Field(default=None, description="Optional feedback note")
    tenant_id: str | None = Field(default=None, description="Tenant boundary")


class IngestDocumentRequest(BaseModel):
    """Payload for ingesting custom documents or datasets with access control."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(..., description="Document or dataset title")
    content: str = Field(..., description="Text content or dataset records")
    document_id: str | None = Field(default=None, description="Optional custom document ID")
    tenant_id: str = Field(default="corp-default", description="Tenant boundary")
    allowed_users: list[str] = Field(
        default_factory=lambda: ["alice", "bob"],
        description="Users granted viewer permission",
    )
    uri: str | None = Field(default=None, description="Optional source link or URI")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchApiRequest(BaseModel):
    """Payload for access-controlled search."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., description="Query text to search")
    principal_id: str = Field(default="anonymous", description="Principal executing search")
    user_id: str | None = Field(default=None, description="Alias for principal_id")
    principal_type: Literal["user", "group", "service"] = Field(default="user")
    tenant_id: str | None = Field(default=None, description="Optional tenant boundary")
    attributes: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=100)
    limit: int | None = Field(default=None, description="Alias for top_k")
    overfetch_factor: float | None = Field(default=None, ge=3.0, le=5.0)
    query_type: str = Field(
        default="factual", description="Query type (factual, navigational, exploratory)"
    )
    chat_history: list[dict[str, str]] | list[ChatTurn] | None = None
    apply_mmr: bool = Field(default=True, description="Apply MMR diversity reordering")
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)
    sparse_query: dict[int, float] | None = None
    pre_filter: dict[str, Any] | None = None


class GroupAliasRequest(BaseModel):
    """Payload for mapping IdP group to canonical group."""

    model_config = ConfigDict(frozen=True)

    idp_group: str = Field(..., description="Source Identity Provider group name")
    canonical_group: str = Field(..., description="Target canonical Zanzibar group identifier")
    tenant_id: str | None = Field(default=None)


class ConnectorActionRequest(BaseModel):
    """Payload for managing or triggering connector sync."""

    model_config = ConfigDict(frozen=True)

    connector_name: str
    action: Literal["sync", "configure"] = "sync"
    config: dict[str, Any] = Field(default_factory=dict)
    initial_cursor: dict[str, Any] | None = None


class SecretCreateRequest(BaseModel):
    """Payload for safely storing an encrypted secret."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Unique secret name or key identifier")
    secret_value: str = Field(..., description="Plaintext secret value to encrypt")
    tenant_id: str | None = Field(default=None)


class AuditLogEntry(BaseModel):
    """Immutable audit trail record for compliance and observability."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(..., description="Category of event (e.g. search, sync, authz)")
    principal_id: str = Field(..., description="Principal who triggered event")
    resource_id: str | None = Field(default=None)
    action: str = Field(..., description="Action name executed")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Storage / State Container ---


class CoreState:
    """In-memory state and dependency container for AegisMind Core services."""

    def __init__(
        self,
        retrieval_pipeline: RetrievalPipeline | None = None,
        authz: AuthzPort | None = None,
        vector_store: VectorStorePort | None = None,
        ingestion_pipeline: IngestionPipelinePort | None = None,
        secret_store: SecretStorePort | None = None,
        llm: LLMPort | None = None,
    ) -> None:
        self.retrieval_pipeline = retrieval_pipeline
        self.authz = authz
        self.vector_store = vector_store or MemoryVectorStoreAdapter()
        self.ingestion_pipeline = ingestion_pipeline
        self.secret_store = secret_store or MemorySecretStore()
        self.llm = llm
        self.scribe_worker = (
            ScribeWorker(pipeline=ingestion_pipeline) if ingestion_pipeline else None
        )

        self.connectors: dict[str, ConnectorPort] = {}
        self.group_aliases: dict[str, str] = {}
        self.audit_log: list[AuditLogEntry] = []
        self.indexed_resources: list[dict[str, Any]] = []
        self.feedback_entries: list[FeedbackEntry] = []

    def record_audit(
        self,
        event_type: str,
        principal_id: str,
        action: str,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        """Append an immutable audit entry."""
        entry = AuditLogEntry(
            event_type=event_type,
            principal_id=principal_id,
            action=action,
            resource_id=resource_id,
            metadata=metadata or {},
        )
        self.audit_log.append(entry)
        return entry


def create_routes(state: CoreState) -> APIRouter:
    """Create configured FastAPI APIRouter containing all core endpoint handlers."""
    router = APIRouter(prefix="/api/v1", tags=["api_v1"])

    # 1. POST /api/v1/search: Access-controlled search
    @router.post("/search", response_model=PipelineResult)
    async def search(req: SearchApiRequest) -> PipelineResult:
        pipeline = state.retrieval_pipeline
        if pipeline is None:
            from aegismind_core.bootstrap import init_default_core_state

            seeded = await init_default_core_state()
            state.retrieval_pipeline = seeded.retrieval_pipeline
            state.authz = seeded.authz
            state.vector_store = seeded.vector_store
            state.connectors = seeded.connectors
            state.indexed_resources = seeded.indexed_resources
            pipeline = seeded.retrieval_pipeline

        if pipeline is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Retrieval pipeline is not configured",
            )

        effective_principal_id = (
            req.user_id if (req.principal_id == "anonymous" and req.user_id) else req.principal_id
        )
        effective_top_k = req.limit if req.limit is not None else req.top_k
        principal = Principal(
            id=effective_principal_id,
            type=req.principal_type,
            tenant_id=req.tenant_id,
            attributes=req.attributes,
        )

        parsed_history: list[ChatTurn] | None = None
        if req.chat_history:
            parsed_history = [
                t if isinstance(t, ChatTurn) else ChatTurn(**t) for t in req.chat_history
            ]

        try:
            with trace_span(
                "agora.search",
                attributes={
                    "query": req.query,
                    "tenant_id": req.tenant_id,
                    "user_id": principal.id,
                },
            ):
                result = await pipeline.execute(
                    query=req.query,
                    principal=principal,
                    chat_history=parsed_history,
                    query_type=req.query_type,
                    sparse_query=req.sparse_query,
                    pre_filter=req.pre_filter,
                    top_k=effective_top_k,
                    overfetch_factor=req.overfetch_factor,
                    apply_mmr=req.apply_mmr,
                    mmr_lambda=req.mmr_lambda,
                )

            state.record_audit(
                event_type="search",
                principal_id=principal.id,
                action="search_query",
                metadata={
                    "query": req.query,
                    "rewritten_query": result.rewritten_query,
                    "query_type": req.query_type,
                    "top_k": effective_top_k,
                    "results_count": len(result.results),
                    "deny_rate": result.deny_rate,
                },
            )
            return result
        except Exception as exc:
            logger.error("Search execution failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Search failed: {exc}",
            ) from exc

    # 2. GET /api/v1/chat: Server-Sent Events (SSE) streaming answers with citations
    @router.get("/chat")
    @router.get("/chat/stream")
    async def chat_sse(
        query: str = Query(..., description="User query for chat session"),
        principal_id: str = Query("anonymous", description="Principal ID"),
        user_id: str | None = Query(None, description="Alias for principal_id"),
        tenant_id: str | None = Query(None, description="Tenant ID"),
        model: str | None = Query(None, description="Ollama model for answer generation"),
        top_k: int = Query(5, ge=1, le=20),
    ) -> StreamingResponse:
        pipeline = state.retrieval_pipeline
        if pipeline is None:
            from aegismind_core.bootstrap import init_default_core_state

            seeded = await init_default_core_state()
            state.retrieval_pipeline = seeded.retrieval_pipeline
            state.authz = seeded.authz
            state.vector_store = seeded.vector_store
            state.connectors = seeded.connectors
            state.indexed_resources = seeded.indexed_resources
            if state.llm is None:
                state.llm = seeded.llm
            pipeline = seeded.retrieval_pipeline

        if pipeline is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Retrieval pipeline is not configured",
            )

        effective_principal_id = (
            user_id if (principal_id == "anonymous" and user_id) else principal_id
        )
        principal = Principal(id=effective_principal_id, type="user", tenant_id=tenant_id)

        async def sse_event_stream() -> AsyncIterator[str]:
            state.record_audit(
                event_type="chat",
                principal_id=effective_principal_id,
                action="chat_sse_stream",
                metadata={"query": query, "model": model},
            )

            # Stage 0: Thinking progress indications
            yield "event: thinking\ndata: Querying vector store with coarse tenant filter...\n\n"
            yield (
                "event: thinking\ndata: Evaluating Zanzibar relationship tuples via "
                "SpiceDB bulk_check...\n\n"
            )
            await asyncio.sleep(0.04)
            yield (
                "event: thinking\ndata: Applying cross-encoder reranker and "
                "synthesizing response...\n\n"
            )
            await asyncio.sleep(0.04)

            # Stage 1: Retrieval through Sacred Pipeline
            with trace_span(
                "agora.chat_retrieval",
                attributes={
                    "query": query,
                    "tenant_id": tenant_id,
                    "user_id": effective_principal_id,
                },
            ):
                res = await pipeline.execute(
                    query=query,
                    principal=principal,
                    top_k=top_k,
                )

            # Stage 2: Formulate prompt for Ollama and fallback synthesis
            if res.results:
                primary = res.results[0]
                answer_parts = [
                    f"Based on verified access-controlled documents for {effective_principal_id}:",
                    primary.text,
                ]
                if len(res.results) > 1:
                    additional_insights = [
                        f"{r.title}: {r.text}"
                        for r in res.results[1:3]
                        if r.document_id != primary.document_id
                    ]
                    if additional_insights:
                        answer_parts.append("Additional context: " + " ".join(additional_insights))
                fallback_answer_text = "\n\n".join(answer_parts)

                context_docs = "\n\n".join(
                    f"[Document: {r.title} (URI: {r.uri})]\n{r.text}" for r in res.results[:5]
                )
                system_prompt = (
                    "You are AegisMind, an enterprise AI assistant with Zanzibar-enforced "
                    "access control.\n"
                    "Answer the user's question clearly, thoroughly, and accurately based on "
                    "the verified documents provided below.\n"
                    "Cite the relevant documents where appropriate, and answer all parts of "
                    "the user's question."
                )
                prompt = f"VERIFIED CONTEXT:\n{context_docs}\n\nUSER QUESTION:\n{query}"
            elif res.total_candidates_evaluated > 0 and res.authorized_candidates_count == 0:
                fallback_answer_text = (
                    f"Access denied: Relevant candidate documents matched query '{query}', but "
                    f"principal '{effective_principal_id}' lacks Zanzibar viewer authorization. "
                    "Under AegisMind zero-leakage security, unauthorized content is strictly "
                    "excluded."
                )
                system_prompt = (
                    "You are AegisMind AI assistant.\n"
                    "Notice: Matching candidate documents exist in the enterprise repository, "
                    "but the user lacks Zanzibar viewer authorization to read them. Mention this "
                    "access boundary briefly, then answer the user's question helpfully using "
                    "general knowledge."
                )
                prompt = f"USER QUESTION:\n{query}"
            else:
                fallback_answer_text = (
                    f"No indexed documents found matching query '{query}'. "
                    f"Please refine your search terms or verify connector sync status."
                )
                system_prompt = (
                    "You are AegisMind, a helpful and knowledgeable enterprise AI assistant.\n"
                    "Answer the user's question clearly, accurately, and thoroughly."
                )
                prompt = f"USER QUESTION:\n{query}"

            # Stage 3: Stream tokens from LLMPort with fallback
            llm_streamed = False
            try:
                llm_adapter = state.llm or get_llm_adapter()
                async for token in llm_adapter.stream_generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model,
                ):
                    llm_streamed = True
                    data = json.dumps({"token": token})
                    yield f"event: token\ndata: {data}\n\n"
            except Exception as exc:
                logger.debug("LLM streaming skipped: %s", exc)

            if not llm_streamed:
                words = fallback_answer_text.split(" ")
                for i, word in enumerate(words):
                    token = word if i == 0 else " " + word
                    data = json.dumps({"token": token})
                    yield f"event: token\ndata: {data}\n\n"
                    await asyncio.sleep(0.015)

            # Stage 3: Stream citations (both array and individual items for maximum compatibility)
            citations = [r.citation.model_dump() for r in res.results if r.citation]
            yield f"event: citations\ndata: {json.dumps(citations)}\n\n"
            for c in citations:
                yield f"event: citation\ndata: {json.dumps(c)}\n\n"

            # Stage 4: Stream done event
            done_payload = json.dumps(
                {
                    "status": "completed",
                    "citations_count": len(citations),
                }
            )
            yield f"event: done\ndata: {done_payload}\n\n"

        return StreamingResponse(sse_event_stream(), media_type="text/event-stream")

    # 3. GET|POST /api/v1/connectors: Spec discovery, configuration, sync triggering
    @router.get("/connectors")
    async def list_connectors() -> dict[str, Any]:
        """Discover available connectors and their configurations."""
        connector_list = []
        for name, conn in state.connectors.items():
            spec: ConnectorSpec = conn.spec()
            connector_list.append(
                {
                    "name": name,
                    "spec": spec.model_dump(),
                }
            )
        return {"connectors": connector_list}

    @router.post("/connectors")
    async def manage_connectors(req: ConnectorActionRequest) -> dict[str, Any]:
        """Trigger sync or configure an existing connector."""
        if req.connector_name not in state.connectors:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Connector '{req.connector_name}' is not registered",
            )

        connector = state.connectors[req.connector_name]

        if req.action == "configure":
            state.record_audit(
                event_type="connector",
                principal_id="admin",
                action="configure_connector",
                resource_id=req.connector_name,
                metadata=req.config,
            )
            return {"status": "configured", "connector": req.connector_name}

        # Action == 'sync'
        if state.scribe_worker is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Scribe worker is not configured",
            )

        run_id = f"sync_{req.connector_name}_{uuid.uuid4().hex[:8]}"
        state.record_audit(
            event_type="connector",
            principal_id="system",
            action="sync_trigger",
            resource_id=req.connector_name,
            metadata={"run_id": run_id},
        )

        report: ScribeSyncReport = await state.scribe_worker.run_sync(
            run_id=run_id,
            connector=connector,
            initial_cursor=req.initial_cursor,
        )

        return {
            "status": "sync_finished",
            "report": report.model_dump(),
        }

    # 4. GET /api/v1/resources: Browsing indexed resources
    @router.get("/resources")
    async def list_resources(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        tenant_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """Browse indexed resources."""
        items = state.indexed_resources
        if tenant_id:
            items = [item for item in items if item.get("tenant_id") == tenant_id]

        total = len(items)
        paged = items[offset : offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "resources": paged,
        }

    # 5. GET|POST /api/v1/group-aliases: Manage identity group mappings
    @router.get("/group-aliases")
    async def list_group_aliases() -> dict[str, Any]:
        """Retrieve registered identity group alias mappings."""
        return {"aliases": state.group_aliases}

    @router.post("/group-aliases")
    async def set_group_alias(req: GroupAliasRequest) -> dict[str, str]:
        """Register or update an identity provider group alias mapping."""
        state.group_aliases[req.idp_group] = req.canonical_group
        state.record_audit(
            event_type="identity",
            principal_id="admin",
            action="set_group_alias",
            metadata={
                "idp_group": req.idp_group,
                "canonical_group": req.canonical_group,
                "tenant_id": req.tenant_id,
            },
        )
        return {
            "status": "created",
            "idp_group": req.idp_group,
            "canonical_group": req.canonical_group,
        }

    # 6. GET /api/v1/audit: Immutable audit log access
    @router.get("/audit")
    async def get_audit_logs(
        principal_id: str | None = Query(None),
        event_type: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """Query immutable audit log entries."""
        entries = state.audit_log
        if principal_id:
            entries = [e for e in entries if e.principal_id == principal_id]
        if event_type:
            entries = [e for e in entries if e.event_type == event_type]

        total = len(entries)
        paged = entries[offset : offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "entries": [e.model_dump() for e in paged],
        }

    # 7. POST & GET /api/v1/secrets: Secrets management
    @router.post("/secrets")
    async def store_secret(req: SecretCreateRequest) -> dict[str, str]:
        """Store an encrypted secret in SecretStore."""
        await state.secret_store.set_secret(req.name, req.secret_value)
        state.record_audit(
            event_type="security",
            principal_id="admin",
            action="store_secret",
            resource_id=req.name,
            metadata={"tenant_id": req.tenant_id},
        )
        return {"status": "stored", "name": req.name}

    @router.get("/secrets/{name}")
    async def get_secret(name: str) -> dict[str, Any]:
        """Retrieve stored secret value."""
        val = await state.secret_store.get_secret(name)
        if val is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Secret '{name}' not found",
            )
        return {"name": name, "value": val}

    # 8. GET /api/v1/models: Model discovery for LLMs
    @router.get("/models")
    async def get_models() -> dict[str, Any]:
        """Discover available LLM models from configured provider."""
        import os

        llm_adapter = state.llm or get_llm_adapter()
        try:
            models = await llm_adapter.list_models()
        except Exception:
            models = []
        active = models[0] if models else getattr(llm_adapter, "default_model", "llama3.2:latest")
        provider = os.environ.get("LLM_PROVIDER", "ollama")
        return {
            "models": models,
            "active_model": active,
            "provider": provider if models else "simulated",
        }

    # 9. POST /api/v1/documents: Custom document and dataset ingestion
    @router.post("/documents")
    async def ingest_document(req: IngestDocumentRequest) -> dict[str, Any]:
        """Ingest custom document or dataset records with Zanzibar viewer access controls."""
        pipeline = state.retrieval_pipeline
        if pipeline is None:
            from aegismind_core.bootstrap import init_default_core_state

            seeded = await init_default_core_state()
            state.retrieval_pipeline = seeded.retrieval_pipeline
            state.authz = seeded.authz
            state.vector_store = seeded.vector_store
            state.connectors = seeded.connectors
            state.indexed_resources = seeded.indexed_resources
            pipeline = seeded.retrieval_pipeline

        if pipeline is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Retrieval pipeline is not configured",
            )

        doc_id = req.document_id or f"doc-custom-{uuid.uuid4().hex[:8]}"
        uri = req.uri or f"dataset://{doc_id}"

        # Segment content into coherent chunks
        paragraphs = [p.strip() for p in req.content.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [req.content.strip()]

        chunks: list[Chunk] = []
        tuples: list[RelationshipTuple] = []

        for idx, text_block in enumerate(paragraphs, start=1):
            embedding = await pipeline.embedder.embed_query(text_block)
            chunk = Chunk(
                id=f"chunk-{doc_id}-{idx:02d}",
                document_id=doc_id,
                index=idx,
                content=text_block,
                embedding=embedding,
                metadata={
                    "title": req.title,
                    "uri": uri,
                    "tenant_id": req.tenant_id,
                    **req.metadata,
                },
                acl=ACL(
                    is_public="anonymous" in req.allowed_users or "*" in req.allowed_users,
                    allowed_principals=[f"user:{u}" for u in req.allowed_users],
                ),
            )
            chunks.append(chunk)

        await state.vector_store.upsert(chunks)

        for u in req.allowed_users:
            tuples.append(
                RelationshipTuple(
                    resource=f"document:{doc_id}",
                    relation="viewer",
                    subject=f"user:{u}",
                )
            )

        if state.authz:
            await state.authz.write_tuples(tuples)

        resource_entry = {
            "id": doc_id,
            "title": req.title,
            "uri": uri,
            "tenant_id": req.tenant_id,
            "chunks_count": len(chunks),
            "allowed_users": req.allowed_users,
            "created_at": datetime.now(UTC).isoformat(),
        }
        state.indexed_resources.insert(0, resource_entry)

        state.record_audit(
            event_type="dataset",
            principal_id="admin",
            action="ingest_custom_dataset",
            resource_id=doc_id,
            metadata={"title": req.title, "chunks_count": len(chunks)},
        )

        return {
            "status": "indexed",
            "document_id": doc_id,
            "title": req.title,
            "chunks_count": len(chunks),
            "allowed_users": req.allowed_users,
        }

    # 10. DELETE /api/v1/documents/{document_id}: Delete dataset and revoke permissions
    @router.delete("/documents/{document_id}")
    async def delete_document(document_id: str) -> dict[str, str]:
        """Delete an ingested dataset and revoke its Zanzibar permissions immediately."""
        if hasattr(state.vector_store, "_chunks"):
            matching_ids = [
                cid
                for cid, c in state.vector_store._chunks.items()
                if getattr(c, "document_id", None) == document_id
            ]
            if matching_ids:
                await state.vector_store.delete(matching_ids)

        if state.authz and hasattr(state.authz, "_tuples"):
            to_delete = [
                RelationshipTuple(resource=res, relation=rel, subject=sub)
                for res, rel, sub in state.authz._tuples
                if res == f"document:{document_id}"
            ]
            if to_delete:
                await state.authz.delete_tuples(to_delete)

        state.indexed_resources = [r for r in state.indexed_resources if r.get("id") != document_id]

        state.record_audit(
            event_type="dataset",
            principal_id="admin",
            action="delete_custom_dataset",
            resource_id=document_id,
        )
        return {"status": "deleted", "document_id": document_id}

    # 11. POST & GET /api/v1/feedback: User thumbs up/down and answer evaluation hook
    @router.post("/feedback", response_model=FeedbackEntry)
    async def submit_feedback(req: FeedbackCreateRequest) -> FeedbackEntry:
        """Store thumbs up/down rating with query, cited chunks, and rewritten query."""
        entry = FeedbackEntry(
            id=f"fb_{uuid.uuid4().hex[:12]}",
            query=req.query,
            rewritten_query=req.rewritten_query,
            retrieved_chunk_ids=req.retrieved_chunk_ids,
            rating=req.rating,
            comment=req.comment,
            tenant_id=req.tenant_id,
        )
        state.feedback_entries.insert(0, entry)
        state.record_audit(
            event_type="feedback",
            principal_id="user",
            action="feedback_submission",
            metadata={
                "feedback_id": entry.id,
                "rating": entry.rating,
                "query": entry.query,
                "chunk_count": len(entry.retrieved_chunk_ids),
            },
        )
        return entry

    @router.get("/feedback")
    async def list_feedback(
        rating: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """Query user feedback entries."""
        items = state.feedback_entries
        if rating:
            items = [item for item in items if item.rating == rating]

        total = len(items)
        paged = items[offset : offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "entries": [e.model_dump() for e in paged],
        }

    # 13. GET /api/v1/metrics: Prometheus metrics endpoint
    @router.get("/metrics", include_in_schema=False)
    def api_metrics() -> Response:
        """Prometheus metrics exposition endpoint."""
        from aegismind_core.observability import render_prometheus_metrics

        return Response(
            content=render_prometheus_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return router
