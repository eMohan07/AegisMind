from __future__ import annotations

import logging
from typing import Any

import httpx

from aegismind_mcp_bridge.models import (
    MCPContentItem,
    MCPRequest,
    MCPResponse,
    MCPTool,
    MCPToolCallResponse,
)

logger = logging.getLogger(__name__)


class MCPClient:
    """Outbound client connecting to external Model Context Protocol servers."""

    def __init__(
        self,
        endpoint_url: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.timeout = timeout
        self.headers = headers or {}
        self._client = http_client

    async def _post_rpc(
        self, method: str, params: dict[str, Any], rpc_id: int = 1
    ) -> dict[str, Any]:
        """Send JSON-RPC message to target MCP server."""
        req = MCPRequest(
            jsonrpc="2.0",
            id=rpc_id,
            method=method,
            params=params,
        )
        should_close = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close = True

        try:
            resp = await client.post(
                self.endpoint_url,
                json=req.model_dump(),
                headers=self.headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data  # type: ignore[no-any-return]
        finally:
            if should_close:
                await client.aclose()

    async def initialize(self) -> dict[str, Any]:
        """Perform MCP initialize handshake."""
        res_data = await self._post_rpc(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "aegismind-relay-client",
                    "version": "0.0.1",
                },
            },
        )
        parsed = MCPResponse.model_validate(res_data)
        if parsed.error:
            raise RuntimeError(f"MCP Initialize failed: {parsed.error}")
        return parsed.result or {}

    async def list_tools(self) -> list[MCPTool]:
        """Discover available tools from the external MCP server."""
        res_data = await self._post_rpc(
            method="tools/list",
            params={},
        )
        parsed = MCPResponse.model_validate(res_data)
        if parsed.error:
            raise RuntimeError(f"tools/list failed: {parsed.error}")
        result = parsed.result or {}
        raw_tools = result.get("tools", [])
        return [MCPTool.model_validate(item) for item in raw_tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolCallResponse:
        """Invoke a tool on the external MCP server."""
        res_data = await self._post_rpc(
            method="tools/call",
            params={"name": name, "arguments": arguments},
        )
        parsed = MCPResponse.model_validate(res_data)
        if parsed.error:
            return MCPToolCallResponse(
                content=[
                    MCPContentItem(
                        type="text",
                        text=f"RPC error from external MCP server: {parsed.error}",
                    )
                ],
                isError=True,
            )
        result = parsed.result or {}
        return MCPToolCallResponse.model_validate(result)
