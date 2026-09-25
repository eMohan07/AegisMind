from __future__ import annotations

import json

import httpx
import pytest
from aegismind_retrieval.adapters_model import LLMQueryRewriterAdapter
from aegismind_types import ChatTurn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegismind_core.adapters.llm import (
    HostedLLMAdapter,
    MockLLMAdapter,
    OllamaAdapter,
    get_llm_adapter,
)
from aegismind_core.ports.llm import LLMPort
from aegismind_core.routes import CoreState, create_routes


def test_llm_port_protocol_conformance() -> None:
    """Verify that all adapters conform to the runtime checkable LLMPort Protocol."""
    ollama = OllamaAdapter(base_url="http://127.0.0.1:11434")
    hosted = HostedLLMAdapter(base_url="https://api.openai.com/v1", api_key="sk-test")
    mock = MockLLMAdapter()

    assert isinstance(ollama, LLMPort)
    assert isinstance(hosted, LLMPort)
    assert isinstance(mock, LLMPort)


@pytest.mark.asyncio
async def test_ollama_adapter_mock_http() -> None:
    """Test OllamaAdapter generation, streaming, token counting, and discovery."""

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        if url_path == "/api/generate":
            body = json.loads(request.content.decode("utf-8"))
            if body.get("stream"):
                content = (
                    b'{"response":"Access-controlled","done":false}\n'
                    b'{"response":" answer","done":false}\n'
                    b'{"response":"","done":true}\n'
                )
                return httpx.Response(200, content=content)
            return httpx.Response(200, json={"response": "Ollama non-streamed response"})

        if url_path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "llama3.2:latest"},
                        {"name": "qwen2.5:7b"},
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = OllamaAdapter(
            base_url="http://mock-ollama:11434",
            model="llama3.2:latest",
            client=http_client,
        )

        # 1. Non-streaming generate
        answer = await adapter.generate("Explain zero-leakage security.")
        assert answer == "Ollama non-streamed response"

        # 2. Streaming generate
        tokens = [t async for t in adapter.stream_generate("Explain zero-leakage security.")]
        assert tokens == ["Access-controlled", " answer"]

        # 3. Token counting and context window
        tokens_count = adapter.count_tokens("Explain zero-leakage security.")
        assert tokens_count >= 3
        assert adapter.get_context_window("llama3.2:latest") == 8192
        assert adapter.get_context_window("llama3-128k") == 131072

        # 4. List models
        models = await adapter.list_models()
        assert models == ["llama3.2:latest", "qwen2.5:7b"]


@pytest.mark.asyncio
async def test_hosted_llm_adapter_openai_compatible() -> None:
    """Test HostedLLMAdapter (vLLM / Together / Azure / OpenAI compatible)."""

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer sk-test-key"
        url_path = request.url.path

        if url_path == "/v1/chat/completions":
            body = json.loads(request.content.decode("utf-8"))
            if body.get("stream"):
                content = (
                    b'data: {"choices":[{"delta":{"content":"Hosted "}}]}\n\n'
                    b'data: {"choices":[{"delta":{"content":"stream"}}]}\n\n'
                    b'data: [DONE]\n\n'
                )
                return httpx.Response(200, content=content)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Hosted LLM completion",
                            }
                        }
                    ]
                },
            )

        if url_path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "gpt-4o-mini"},
                        {"id": "meta-llama/Meta-Llama-3-70B-Instruct"},
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = HostedLLMAdapter(
            base_url="https://api.openai.com/v1",
            api_key="sk-test-key",
            model="gpt-4o-mini",
            client=http_client,
        )

        # 1. Non-streaming generate
        answer = await adapter.generate("Test prompt")
        assert answer == "Hosted LLM completion"

        # 2. Streaming generate
        tokens = [t async for t in adapter.stream_generate("Test prompt")]
        assert tokens == ["Hosted ", "stream"]

        # 3. Token counting and context window
        count = adapter.count_tokens("Test prompt with multiple tokens")
        assert count >= 4
        assert adapter.get_context_window("gpt-4o") == 128000

        # 4. List models
        models = await adapter.list_models()
        assert models == ["gpt-4o-mini", "meta-llama/Meta-Llama-3-70B-Instruct"]


def test_factory_configuration_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that get_llm_adapter selects the correct provider based on environment variables."""
    # Test ollama provider
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.2:1b")
    ollama_inst = get_llm_adapter()
    assert isinstance(ollama_inst, OllamaAdapter)
    assert ollama_inst.default_model == "llama3.2:1b"

    # Test hosted provider
    monkeypatch.setenv("LLM_PROVIDER", "hosted")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.together.xyz/v1")
    monkeypatch.setenv("LLM_MODEL", "togethercomputer/llama-3-8b")
    monkeypatch.setenv("LLM_API_KEY", "xyz-token")
    hosted_inst = get_llm_adapter()
    assert isinstance(hosted_inst, HostedLLMAdapter)
    assert hosted_inst.base_url == "https://api.together.xyz/v1"
    assert hosted_inst.default_model == "togethercomputer/llama-3-8b"
    assert hosted_inst.api_key == "xyz-token"

    # Test mock provider
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    mock_inst = get_llm_adapter()
    assert isinstance(mock_inst, MockLLMAdapter)


@pytest.mark.asyncio
async def test_llm_query_rewriter_adapter() -> None:
    """Test LLMQueryRewriterAdapter using an underlying LLMPort."""
    mock_llm = MockLLMAdapter(default_response="Standalone zero-leakage security query")
    rewriter = LLMQueryRewriterAdapter(llm=mock_llm)

    history = [
        ChatTurn(role="user", content="Tell me about the SEC-892 ticket."),
        ChatTurn(role="assistant", content="SEC-892 enforces zero stale read revocation."),
    ]
    rewritten = await rewriter.rewrite_query("what about its caching policy?", history=history)
    assert rewritten == "Standalone zero-leakage security query"
    assert len(mock_llm.generated_prompts) == 1
    assert "what about its caching policy?" in str(mock_llm.generated_prompts[0]["prompt"])


def test_api_routes_consume_llm_port() -> None:
    """Test that FastAPI routes (/models and /chat/stream) consume the configured LLMPort."""
    mock_llm = MockLLMAdapter(
        default_response="Verified answer token streamed from LLMPort.",
        models=["custom-llm-v1", "custom-llm-v2"],
    )

    from aegismind_authz.adapters.memory import MemoryAuthzAdapter
    from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
    from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
    from aegismind_retrieval.pipeline import RetrievalPipeline

    pipeline = RetrievalPipeline(
        authz=MemoryAuthzAdapter(),
        vector_store=MemoryVectorStoreAdapter(),
        embedder=MockEmbedderAdapter(),
        reranker=MockRerankerAdapter(),
    )

    state = CoreState(retrieval_pipeline=pipeline, llm=mock_llm)
    router = create_routes(state)
    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)

    # 1. Test /api/v1/models queries LLMPort
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["models"] == ["custom-llm-v1", "custom-llm-v2"]
    assert data["active_model"] == "custom-llm-v1"

    # 2. Test /api/v1/chat/stream consumes LLMPort stream_generate
    stream_resp = client.get(
        "/api/v1/chat/stream",
        params={"query": "test query", "principal_id": "alice"},
    )
    assert stream_resp.status_code == 200
    assert "event: token" in stream_resp.text
    assert '"token": "Verified"' in stream_resp.text
    assert '"token": " streamed"' in stream_resp.text
