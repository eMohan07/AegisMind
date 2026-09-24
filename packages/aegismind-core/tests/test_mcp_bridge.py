from __future__ import annotations

from typing import Any

import httpx
import pytest
from aegismind_authz.ports import AuthzPort, CheckRequest
from aegismind_mcp_bridge import MCPBridgeServer, MCPClient, MCPTool, MCPToolCallResponse
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import Chunk, Principal, TokenConsistency

from aegismind_core.app import create_app
from aegismind_core.routes import CoreState


class MockAuthz(AuthzPort):
    async def bulk_check(
        self,
        requests: list[CheckRequest],
        consistency: TokenConsistency | None = None,
    ) -> list[bool]:
        return [True for _ in requests]

    async def write_tuples(self, tuples: list[Any]) -> TokenConsistency:
        return TokenConsistency(token="zed_mock")

    async def delete_tuples(self, tuples: list[Any]) -> TokenConsistency:
        return TokenConsistency(token="zed_mock")

    async def check_permission(self, subject: Principal, relation: str, resource: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_mcp_endpoints_and_jsonrpc() -> None:
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=8)
    reranker = MockRerankerAdapter()
    authz = MockAuthz()

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    # Ingest a sample chunk
    chunk = Chunk(
        id="c_mcp",
        document_id="doc_mcp",
        content="Enterprise zero-trust architecture document with fine-grained ACLs.",
        embedding=[0.1] * 8,
        metadata={"title": "Zero Trust Blueprint", "uri": "https://wiki/zerotrust"},
    )
    await vector_store.upsert([chunk])

    state = CoreState(
        retrieval_pipeline=pipeline,
        authz=authz,
        vector_store=vector_store,
    )
    app = create_app(state)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test tools list endpoint
        tools_resp = await client.get("/mcp/tools")
        assert tools_resp.status_code == 200
        tools_data = tools_resp.json()
        assert len(tools_data["tools"]) >= 1
        assert tools_data["tools"][0]["name"] == "aegismind_search"

        # 2. Test JSON-RPC initialize
        init_rpc = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        }
        rpc_init_resp = await client.post("/mcp/rpc", json=init_rpc)
        assert rpc_init_resp.status_code == 200
        init_data = rpc_init_resp.json()
        assert init_data["result"]["protocolVersion"] == "2024-11-05"

        # 3. Test JSON-RPC tools/list
        list_rpc = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        rpc_list_resp = await client.post("/mcp/rpc", json=list_rpc)
        assert rpc_list_resp.status_code == 200
        assert len(rpc_list_resp.json()["result"]["tools"]) >= 1

        # 4. Test JSON-RPC tools/call
        call_rpc = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "aegismind_search",
                "arguments": {
                    "query": "zero-trust architecture",
                    "top_k": 3,
                },
            },
        }
        rpc_call_resp = await client.post("/mcp/rpc", json=call_rpc)
        assert rpc_call_resp.status_code == 200
        call_result = rpc_call_resp.json()["result"]
        assert call_result["isError"] is False
        assert "Zero Trust Blueprint" in call_result["content"][0]["text"]

        # 5. Direct tool call endpoint
        direct_resp = await client.post(
            "/mcp/tools/aegismind_search",
            json={
                "arguments": {"query": "zero-trust architecture"},
                "principal_id": "alice",
            },
        )
        assert direct_resp.status_code == 200
        direct_data = direct_resp.json()
        assert direct_data["isError"] is False
        assert len(direct_data["content"]) > 0


@pytest.mark.asyncio
async def test_mcp_client_bridge() -> None:
    server = MCPBridgeServer(name="test-server")

    async def echo_handler(args: dict[str, Any]) -> MCPToolCallResponse:
        from aegismind_mcp_bridge.models import MCPContentItem

        return MCPToolCallResponse(
            content=[MCPContentItem(type="text", text=f"Echo: {args.get('msg')}")]
        )

    server.register_tool(
        tool=MCPTool(
            name="echo",
            description="Echo back input",
            inputSchema={"type": "object", "properties": {"msg": {"type": "string"}}},
        ),
        handler=echo_handler,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode("utf-8"))
        res = await server.handle_jsonrpc(body)
        return httpx.Response(200, json=res)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MCPClient(endpoint_url="http://mock-mcp/rpc", http_client=http_client)
        init_res = await client.initialize()
        assert init_res["protocolVersion"] == "2024-11-05"

        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "echo"

        call_res = await client.call_tool("echo", {"msg": "Hello MCP"})
        assert call_res.isError is False
        assert call_res.content[0].text == "Echo: Hello MCP"
