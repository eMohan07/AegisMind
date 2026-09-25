from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from aegismind_core.observability import trace_span

logger = logging.getLogger(__name__)


def _get_candidate_ollama_urls() -> list[str]:
    """Get list of candidate Ollama URLs in priority order."""
    env_url = os.environ.get("LLM_BASE_URL") or os.environ.get("OLLAMA_URL")
    urls = []
    if env_url:
        urls.append(env_url.rstrip("/"))
    urls.extend(
        [
            "http://host.docker.internal:11434",
            "http://localhost:11434",
            "http://127.0.0.1:11434",
        ]
    )
    seen: set[str] = set()
    result = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


async def _find_active_ollama_url() -> str | None:
    """Find the first responsive Ollama endpoint."""
    candidates = _get_candidate_ollama_urls()
    async with httpx.AsyncClient(timeout=1.5) as client:
        for url in candidates:
            try:
                resp = await client.get(f"{url}/api/tags")
                if resp.status_code == 200:
                    return url
            except Exception as exc:
                logger.debug("Ollama candidate endpoint %s not responsive: %s", url, exc)
                continue
    return None


class OllamaAdapter:
    """Local development LLM adapter connecting to Ollama."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        context_window: int = 8192,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._configured_base_url = base_url
        self.default_model = (
            model
            or os.environ.get("LLM_MODEL")
            or os.environ.get("OLLAMA_MODEL")
            or "llama3.2:latest"
        )
        self.default_context_window = int(os.environ.get("LLM_CONTEXT_WINDOW", str(context_window)))
        self._client = client

    async def _resolve_base_url(self) -> str:
        if self._configured_base_url:
            return self._configured_base_url.rstrip("/")
        active = await _find_active_ollama_url()
        return active or "http://127.0.0.1:11434"

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate a complete text completion using Ollama /api/generate."""
        chosen_model = model or self.default_model
        base_url = await self._resolve_base_url()
        payload: dict[str, Any] = {
            "model": chosen_model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt
        options: dict[str, Any] = {}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if temperature is not None:
            options["temperature"] = temperature
        if options:
            payload["options"] = options

        with trace_span(
            "llm.ollama.generate",
            attributes={"llm.model": chosen_model, "llm.endpoint": base_url},
        ):
            if self._client is not None:
                resp = await self._client.post(
                    f"{base_url}/api/generate", json=payload, timeout=60.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return str(data.get("response", "")).strip()
                logger.warning("Ollama generate returned status %d", resp.status_code)
                return ""

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{base_url}/api/generate", json=payload, timeout=60.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return str(data.get("response", "")).strip()
                logger.warning("Ollama generate returned status %d", resp.status_code)
                return ""

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens from Ollama."""
        chosen_model = model or self.default_model
        base_url = await self._resolve_base_url()

        payload: dict[str, Any] = {
            "model": chosen_model,
            "prompt": prompt,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt
        options: dict[str, Any] = {}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if temperature is not None:
            options["temperature"] = temperature
        if options:
            payload["options"] = options

        with trace_span(
            "llm.ollama.stream_generate",
            attributes={"llm.model": chosen_model, "llm.endpoint": base_url},
        ):
            if self._client is not None:
                async with self._client.stream(
                    "POST", f"{base_url}/api/generate", json=payload
                ) as response:
                    if response.status_code != 200:
                        logger.warning("Ollama stream returned status %d", response.status_code)
                        return
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                yield token
                            if data.get("done", False):
                                break
                        except Exception as exc:
                            logger.debug("Error parsing Ollama chunk: %s", exc)
            else:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST", f"{base_url}/api/generate", json=payload
                    ) as response:
                        if response.status_code != 200:
                            logger.warning("Ollama stream returned status %d", response.status_code)
                            return
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                token = data.get("response", "")
                                if token:
                                    yield token
                                if data.get("done", False):
                                    break
                            except Exception as exc:
                                logger.debug("Error parsing Ollama chunk: %s", exc)

    def count_tokens(self, text: str, model: str | None = None) -> int:
        """Count tokens using tiktoken cl100k_base with character approximation fallback."""
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            return max(1, math.ceil(len(text) / 4))

    def get_context_window(self, model: str | None = None) -> int:
        """Return context window capacity for model."""
        target_model = (model or self.default_model).lower()
        if "128k" in target_model:
            return 131072
        if "32k" in target_model:
            return 32768
        if "16k" in target_model:
            return 16384
        return self.default_context_window

    async def list_models(self) -> list[str]:
        """Discover available models from Ollama."""
        base_url = await self._resolve_base_url()
        try:
            if self._client is not None:
                resp = await self._client.get(f"{base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            else:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{base_url}/api/tags")
                    if resp.status_code == 200:
                        data = resp.json()
                        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception as exc:
            logger.debug("Failed listing Ollama models: %s", exc)
        return []
