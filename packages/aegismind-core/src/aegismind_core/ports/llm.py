from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMPort(Protocol):
    """Port for LLM generation, streaming, token counting, and context window queries."""

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate a complete text completion."""
        ...

    def stream_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens asynchronously."""
        ...

    def count_tokens(self, text: str, model: str | None = None) -> int:
        """Count the number of tokens in a text string."""
        ...

    def get_context_window(self, model: str | None = None) -> int:
        """Return the maximum context window token capacity for the model."""
        ...

    async def list_models(self) -> list[str]:
        """Return a list of available model names supported by the provider."""
        ...
