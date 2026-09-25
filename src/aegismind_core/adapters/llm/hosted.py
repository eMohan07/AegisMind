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


class HostedLLMAdapter:
    """OpenAI-compatible hosted LLM adapter supporting vLLM, Together, Azure, and OpenAI."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        context_window: int = 128000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        raw_url = base_url or os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1"
        self.base_url = raw_url.rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.default_model = model or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
        self.default_context_window = int(
            os.environ.get("LLM_CONTEXT_WINDOW", str(context_window))
        )
        self._client = client

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate text completion via OpenAI-compatible /chat/completions."""
        chosen_model = model or self.default_model
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        with trace_span(
            "llm.hosted.generate",
            attributes={"llm.model": chosen_model, "llm.endpoint": self.base_url},
        ):
            headers = self._get_headers()
            if self._client is not None:
                resp = await self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return str(choices[0].get("message", {}).get("content", "")).strip()
                logger.warning("Hosted LLM generate returned status %d", resp.status_code)
                return ""

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return str(choices[0].get("message", {}).get("content", "")).strip()
                logger.warning("Hosted LLM generate returned status %d", resp.status_code)
                return ""

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens via OpenAI-compatible SSE /chat/completions."""
        chosen_model = model or self.default_model
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        headers = self._get_headers()
        headers["Accept"] = "text/event-stream"

        with trace_span(
            "llm.hosted.stream_generate",
            attributes={"llm.model": chosen_model, "llm.endpoint": self.base_url},
        ):
            if self._client is not None:
                async with self._client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        logger.warning(
                            "Hosted LLM stream returned status %d", response.status_code
                        )
                        return
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        line_str = line.strip()
                        if line_str.startswith("data: "):
                            raw_data = line_str[6:].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                data = json.loads(raw_data)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except Exception as exc:
                                logger.debug("Error parsing hosted LLM chunk: %s", exc)
            else:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            logger.warning(
                                "Hosted LLM stream returned status %d", response.status_code
                            )
                            return
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            line_str = line.strip()
                            if line_str.startswith("data: "):
                                raw_data = line_str[6:].strip()
                                if raw_data == "[DONE]":
                                    break
                                try:
                                    data = json.loads(raw_data)
                                    choices = data.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                except Exception as exc:
                                    logger.debug("Error parsing hosted LLM chunk: %s", exc)

    def count_tokens(self, text: str, model: str | None = None) -> int:
        """Count tokens using tiktoken with character approximation fallback."""
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            return max(1, math.ceil(len(text) / 4))

    def get_context_window(self, model: str | None = None) -> int:
        """Return context window capacity for model."""
        target_model = (model or self.default_model).lower()
        if "128k" in target_model or "gpt-4" in target_model:
            return 128000
        if "32k" in target_model:
            return 32768
        if "16k" in target_model:
            return 16384
        if "8k" in target_model:
            return 8192
        return self.default_context_window

    async def list_models(self) -> list[str]:
        """Discover available models from OpenAI-compatible /models endpoint."""
        try:
            headers = self._get_headers()
            if self._client is not None:
                resp = await self._client.get(
                    f"{self.base_url}/models",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            else:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(
                        f"{self.base_url}/models",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        except Exception as exc:
            logger.debug("Failed listing hosted LLM models: %s", exc)
        return []
