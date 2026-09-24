from __future__ import annotations

import logging
from typing import Any

from aegismind_mcp_bridge import (
    MCPBridgeServer,
    MCPContentItem,
    MCPToolCallRequest,
    MCPToolCallResponse,
    create_search_tool_spec,
)
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import Principal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class DirectToolCallPayload(BaseModel):
    """Payload for invoking an MCP tool directly via HTTP."""

    model_config = ConfigDict(frozen=True)

    arguments: dict[str, Any] = Field(default_factory=dict)
    principal_id: str = Field(default="system")
    tenant_id: str | None = Field(default=None)


def create_mcp_router(
    pipeline: RetrievalPipeline | None = None,
    server: MCPBridgeServer | None = None,
    state: Any | None = None,
) -> APIRouter:
    """Create FastAPI router for native Model Context Protocol integration."""
    router = APIRouter(prefix="/mcp", tags=["mcp"])
    bridge_server = server or MCPBridgeServer(name="aegismind-core-mcp")

    if pipeline is not None or state is not None:

        async def _search_handler(args: dict[str, Any]) -> MCPToolCallResponse:
            active_pipeline = pipeline or (
                getattr(state, "retrieval_pipeline", None) if state else None
            )
            if active_pipeline is None:
                return MCPToolCallResponse(
                    content=[
                        MCPContentItem(
                            type="text",
                            text="Retrieval pipeline is currently uninitialized.",
                        )
                    ],
                    is_error=True,
                )
            query = str(args.get("query", ""))
            top_k = int(args.get("top_k", 5))
            tenant_id = args.get("tenant_id")
            principal_id = str(args.get("principal_id", "mcp-user"))

            principal = Principal(id=principal_id, type="user", tenant_id=tenant_id)
            res = await active_pipeline.execute(
                query=query,
                principal=principal,
                top_k=top_k,
            )

            text_lines = [f"Found {len(res.results)} results for query: '{query}'\n"]
            for idx, r in enumerate(res.results, 1):
                text_lines.append(f"{idx}. [{r.title}]({r.uri}) (Score: {r.score:.2f})")
                text_lines.append(f"   {r.text}\n")

            return MCPToolCallResponse(
                content=[
                    MCPContentItem(
                        type="text",
                        text="\n".join(text_lines),
                    )
                ]
            )

        bridge_server.register_tool(
            tool=create_search_tool_spec(),
            handler=_search_handler,
        )

    @router.post("/rpc")
    async def rpc_endpoint(request: Request) -> dict[str, Any]:
        """Model Context Protocol JSON-RPC 2.0 dispatch endpoint."""
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

        return await bridge_server.handle_jsonrpc(body)

    @router.get("/tools")
    async def list_tools() -> dict[str, Any]:
        """List all tools exposed by AegisMind MCP server."""
        tools = bridge_server.list_tools()
        return {"tools": [t.model_dump() for t in tools]}

    @router.post("/tools/{tool_name}")
    async def invoke_tool(tool_name: str, payload: DirectToolCallPayload) -> MCPToolCallResponse:
        """Directly invoke an MCP tool with arguments."""
        merged_args = dict(payload.arguments)
        merged_args.setdefault("principal_id", payload.principal_id)
        if payload.tenant_id:
            merged_args.setdefault("tenant_id", payload.tenant_id)

        req = MCPToolCallRequest(name=tool_name, arguments=merged_args)
        return await bridge_server.call_tool(req)

    return router
