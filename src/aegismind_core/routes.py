from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from aegismind_authz.ports import AuthzPort
from aegismind_connector_sdk.ports import ConnectorPort, ConnectorSpec
from aegismind_infra.ports import SecretStorePort
from aegismind_infra.secrets import MemorySecretStore
from aegismind_ingestion.ports import IngestionPipelinePort
from aegismind_ingestion.worker import ScribeSyncReport, ScribeWorker
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import PipelineResult, RetrievalPipeline
from aegismind_retrieval.ports import VectorStorePort
from aegismind_types import (
    Principal,
)
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# --- Domain Models for API ---


class SearchApiRequest(BaseModel):
    """Payload for access-controlled search."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., description="Query text to search")
    principal_id: str = Field(default="anonymous", description="Principal executing search")
    principal_type: Literal["user", "group", "service"] = Field(default="user")
    tenant_id: str | None = Field(default=None, description="Optional tenant boundary")
    attributes: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=100)
    overfetch_factor: float = Field(default=4.0, ge=3.0, le=5.0)
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
    ) -> None:
        self.retrieval_pipeline = retrieval_pipeline
        self.authz = authz
        self.vector_store = vector_store or MemoryVectorStoreAdapter()
        self.ingestion_pipeline = ingestion_pipeline
        self.secret_store = secret_store or MemorySecretStore()
        self.scribe_worker = (
            ScribeWorker(pipeline=ingestion_pipeline) if ingestion_pipeline else None
        )

        self.connectors: dict[str, ConnectorPort] = {}
        self.group_aliases: dict[str, str] = {}
        self.audit_log: list[AuditLogEntry] = []
        self.indexed_resources: list[dict[str, Any]] = []

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
        if state.retrieval_pipeline is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Retrieval pipeline is not configured",
            )

        principal = Principal(
            id=req.principal_id,
            type=req.principal_type,
            tenant_id=req.tenant_id,
            attributes=req.attributes,
        )

        try:
            result = await state.retrieval_pipeline.execute(
                query=req.query,
                principal=principal,
                sparse_query=req.sparse_query,
                pre_filter=req.pre_filter,
                top_k=req.top_k,
                overfetch_factor=req.overfetch_factor,
            )

            state.record_audit(
                event_type="search",
                principal_id=principal.id,
                action="search_query",
                metadata={
                    "query": req.query,
                    "top_k": req.top_k,
                    "results_count": len(result.results),
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
    async def chat_sse(
        query: str = Query(..., description="User query for chat session"),
        principal_id: str = Query("anonymous", description="Principal ID"),
        tenant_id: str | None = Query(None, description="Tenant ID"),
        top_k: int = Query(5, ge=1, le=20),
    ) -> StreamingResponse:
        if state.retrieval_pipeline is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Retrieval pipeline is not configured",
            )

        pipeline = state.retrieval_pipeline
        principal = Principal(id=principal_id, type="user", tenant_id=tenant_id)

        async def sse_event_stream() -> AsyncIterator[str]:
            state.record_audit(
                event_type="chat",
                principal_id=principal_id,
                action="chat_sse_stream",
                metadata={"query": query},
            )

            # Stage 1: Retrieval
            res = await pipeline.execute(
                query=query,
                principal=principal,
                top_k=top_k,
            )

            # Stage 2: Stream answer tokens
            answer_text = (
                f"Synthesized response for query '{query}': "
                f"Evaluated {res.total_candidates_evaluated} candidates with "
                f"{res.authorized_candidates_count} passing authorization."
            )
            words = answer_text.split(" ")
            for word in words:
                data = json.dumps({"token": word + " "})
                yield f"event: token\ndata: {data}\n\n"
                await asyncio.sleep(0.005)

            # Stage 3: Stream citations
            for r in res.results:
                if r.citation:
                    citation_data = json.dumps(r.citation.model_dump())
                    yield f"event: citation\ndata: {citation_data}\n\n"

            # Stage 4: Stream done event
            done_payload = json.dumps(
                {
                    "status": "completed",
                    "citations_count": len(res.results),
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

    return router
