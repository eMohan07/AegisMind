from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aegismind_mcp_bridge.models import (
    MCPContentItem,
    MCPRequest,
    MCPResponse,
    MCPTool,
    MCPToolCallRequest,
    MCPToolCallResponse,
)

logger = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], Awaitable[MCPToolCallResponse] | MCPToolCallResponse]

DEFAULT_ACTION_ALLOWLIST: set[str] = {
    "aegismind_search",
    "aegismind_read",
    "aegismind_list",
}


class MCPBridgeServer:
    """Model Context Protocol server bridge exposing tools and handling JSON-RPC calls."""

    def __init__(
        self,
        name: str = "aegismind-mcp-bridge",
        version: str = "0.0.1",
        allowed_actions: set[str] | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.allowed_actions = set(allowed_actions or DEFAULT_ACTION_ALLOWLIST)
        self._tools: dict[str, MCPTool] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register_tool(
        self,
        tool: MCPTool,
        handler: ToolHandler,
    ) -> None:
        """Register a new MCP tool definition and its execution handler."""
        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler
        logger.debug("Registered MCP tool: %s", tool.name)

    def list_tools(self) -> list[MCPTool]:
        """Return list of all registered MCP tools."""
        return list(self._tools.values())

    async def call_tool(self, request: MCPToolCallRequest) -> MCPToolCallResponse:
        """Execute a tool by name with arguments and output-side action validation."""
        if request.name not in self._handlers:
            return MCPToolCallResponse(
                content=[
                    MCPContentItem(
                        type="text",
                        text=f"Tool '{request.name}' not found",
                    )
                ],
                isError=True,
            )

        # Output-side validation: enforce allowlist for agentic actions beyond read/search
        if request.name not in self.allowed_actions:
            confirmed = bool(request.arguments.get("confirmed", False))
            if not confirmed:
                logger.warning(
                    "Blocked non-allowlisted MCP action without explicit confirmation: tool='%s'",
                    request.name,
                )
                return MCPToolCallResponse(
                    content=[
                        MCPContentItem(
                            type="text",
                            text=(
                                f"Agentic action '{request.name}' blocked: Actions beyond "
                                "read/search require explicit confirmation (confirmed=True) "
                                "to prevent indirect prompt injection execution."
                            ),
                        )
                    ],
                    isError=True,
                )

        handler = self._handlers[request.name]
        try:
            res = handler(request.arguments)
            if hasattr(res, "__await__"):
                return await res
            return res
        except Exception as exc:
            logger.error("Error executing MCP tool '%s': %s", request.name, exc)
            return MCPToolCallResponse(
                content=[
                    MCPContentItem(
                        type="text",
                        text=f"Execution error in '{request.name}': {exc}",
                    )
                ],
                isError=True,
            )

    async def handle_jsonrpc(
        self,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a JSON-RPC 2.0 message conforming to Model Context Protocol."""
        try:
            req = MCPRequest.model_validate(payload)
        except Exception as exc:
            return MCPResponse(
                id=payload.get("id"),
                error={
                    "code": -32600,
                    "message": f"Invalid JSON-RPC Request: {exc}",
                },
            ).model_dump(exclude_none=True)

        if req.method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": self.name,
                    "version": self.version,
                },
            }
            return MCPResponse(id=req.id, result=result).model_dump(exclude_none=True)

        if req.method == "notifications/initialized":
            return MCPResponse(id=req.id, result={}).model_dump(exclude_none=True)

        if req.method == "tools/list":
            tools_data = [t.model_dump() for t in self.list_tools()]
            return MCPResponse(id=req.id, result={"tools": tools_data}).model_dump(
                exclude_none=True
            )

        if req.method == "tools/call":
            tool_name = str(req.params.get("name", ""))
            tool_args = req.params.get("arguments", {})
            if not isinstance(tool_args, dict):
                return MCPResponse(
                    id=req.id,
                    error={"code": -32602, "message": "arguments must be an object"},
                ).model_dump(exclude_none=True)

            call_req = MCPToolCallRequest(name=tool_name, arguments=tool_args)
            call_res = await self.call_tool(call_req)
            return MCPResponse(id=req.id, result=call_res.model_dump()).model_dump(
                exclude_none=True
            )

        return MCPResponse(
            id=req.id,
            error={
                "code": -32601,
                "message": f"Method '{req.method}' not found",
            },
        ).model_dump(exclude_none=True)


def create_search_tool_spec() -> MCPTool:
    """Create the canonical AegisMind knowledge search MCP tool definition."""
    return MCPTool(
        name="aegismind_search",
        description=(
            "Search enterprise documents and knowledge with fine-grained access control "
            "and deep-linked citations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search for",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of relevant chunks to retrieve",
                    "default": 5,
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Optional tenant boundary identifier",
                },
            },
            "required": ["query"],
        },
    )
