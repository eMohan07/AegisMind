from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from aegismind_core.domain.models import Chunk, RetrievalQuery, RetrievalResult
from aegismind_core.domain.permissions import (
    Resource,
    Subject,
)
from aegismind_core.services.retrieval import RetrievalService

logger = logging.getLogger("aegismind.api")

app = FastAPI(
    title="AegisMind API",
    description="Enterprise knowledge platform with Zanzibar access control at retrieval",
    version="0.1.0",
)

# Instantiate retrieval service using registry-resolved adapters
service = RetrievalService()


class RelationshipRequest(BaseModel):
    subject_type: str = Field(default="user")
    subject_id: str
    subject_relation: str | None = None
    relation: str
    resource_type: str = Field(default="document")
    resource_id: str


class DocumentIngestRequest(BaseModel):
    document_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect portal root to interactive documentation."""
    return RedirectResponse(url="/docs")


@app.get("/healthz")
async def health_check() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": "AegisMind"}


@app.post("/api/v1/search", response_model=RetrievalResult)
async def search(query: RetrievalQuery) -> RetrievalResult:
    """Execute permission-guarded retrieval."""
    try:
        return await service.search(query)
    except Exception as exc:
        logger.error("Search request error: %s", exc)
        raise HTTPException(status_code=500, detail="Search execution failed") from exc


@app.post("/api/v1/relationships")
async def write_relationship(req: RelationshipRequest) -> dict[str, str]:
    """Write relationship tuple for Zanzibar authorization."""
    try:
        subject = Subject(
            type=req.subject_type,
            id=req.subject_id,
            relation=req.subject_relation,
        )
        resource = Resource(type=req.resource_type, id=req.resource_id)
        token = await service._authz.write_relationship(
            subject=subject,
            relation=req.relation,
            resource=resource,
        )
        return {"status": "created", "zed_token": token}
    except Exception as exc:
        logger.error("Failed writing relationship: %s", exc)
        raise HTTPException(status_code=500, detail="Failed writing relationship") from exc


@app.delete("/api/v1/relationships")
async def delete_relationship(req: RelationshipRequest) -> dict[str, str]:
    """Delete relationship tuple from Zanzibar engine."""
    try:
        subject = Subject(
            type=req.subject_type,
            id=req.subject_id,
            relation=req.subject_relation,
        )
        resource = Resource(type=req.resource_type, id=req.resource_id)
        token = await service._authz.delete_relationship(
            subject=subject,
            relation=req.relation,
            resource=resource,
        )
        return {"status": "deleted", "zed_token": token}
    except Exception as exc:
        logger.error("Failed deleting relationship: %s", exc)
        raise HTTPException(status_code=500, detail="Failed deleting relationship") from exc


@app.post("/api/v1/documents")
async def ingest_document(req: DocumentIngestRequest) -> dict[str, str]:
    """Ingest and index a document chunk into vector storage."""
    try:
        embedding = await service._embedder.embed_query(req.content)
        chunk = Chunk(
            id=f"chunk_{req.document_id}",
            document_id=req.document_id,
            content=req.content,
            chunk_index=0,
            embedding=embedding,
            metadata=req.metadata,
        )
        await service._vector_store.upsert([chunk])
        return {"status": "ingested", "chunk_id": chunk.id}
    except Exception as exc:
        logger.error("Failed ingesting document: %s", exc)
        raise HTTPException(status_code=500, detail="Failed ingesting document") from exc
