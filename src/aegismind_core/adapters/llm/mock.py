from __future__ import annotations

import math
from collections.abc import AsyncIterator


class MockLLMAdapter:
    """Mock LLM adapter for deterministic unit testing and offline development."""

    def __init__(
        self,
        default_response: str = (
            "Mock generated answer based on verified access-controlled context."
        ),
        context_window: int = 8192,
        models: list[str] | None = None,
    ) -> None:
        self.default_response = default_response
        self.context_window = context_window
        self.models = models or ["mock-llama-3.2", "mock-gpt-4o"]
        self.generated_prompts: list[dict[str, str | None]] = []

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        self.generated_prompts.append({"prompt": prompt, "system": system_prompt, "model": model})
        return self.default_response

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        self.generated_prompts.append({"prompt": prompt, "system": system_prompt, "model": model})
        words = self.default_response.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            yield token

    def count_tokens(self, text: str, model: str | None = None) -> int:
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            return max(1, math.ceil(len(text) / 4))

    def get_context_window(self, model: str | None = None) -> int:
        return self.context_window

    async def list_models(self) -> list[str]:
        return list(self.models)
