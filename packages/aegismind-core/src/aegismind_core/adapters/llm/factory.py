from __future__ import annotations

import logging
import os

from aegismind_core.adapters.llm.hosted import HostedLLMAdapter
from aegismind_core.adapters.llm.mock import MockLLMAdapter
from aegismind_core.adapters.llm.ollama import OllamaAdapter
from aegismind_core.ports.llm import LLMPort

logger = logging.getLogger(__name__)


def get_llm_adapter(provider: str | None = None) -> LLMPort:
    """Instantiate and return the configured LLMPort adapter.

    Configuration is driven by environment variables:
      LLM_PROVIDER: 'ollama' (default) or 'hosted' / 'openai' or 'mock'
      LLM_BASE_URL: custom endpoint URL (fallback to OLLAMA_URL if provider=ollama)
      LLM_MODEL: model identifier (fallback to OLLAMA_MODEL)
      LLM_API_KEY: optional API key for hosted providers
      LLM_CONTEXT_WINDOW: token limit for context window
    """
    selected_provider = (
        provider or os.environ.get("LLM_PROVIDER") or "ollama"
    ).lower().strip()

    if selected_provider in {"hosted", "openai", "vllm", "together", "azure"}:
        base_url = os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1"
        api_key = os.environ.get("LLM_API_KEY", "")
        model = os.environ.get("LLM_MODEL") or "gpt-4o-mini"
        logger.info(
            "Configuring HostedLLMAdapter (endpoint=%s, model=%s)",
            base_url,
            model,
        )
        return HostedLLMAdapter(base_url=base_url, api_key=api_key, model=model)

    if selected_provider == "mock":
        logger.info("Configuring MockLLMAdapter")
        return MockLLMAdapter()

    # Default to Ollama adapter
    ollama_base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("OLLAMA_URL")
    ollama_model = os.environ.get("LLM_MODEL") or os.environ.get("OLLAMA_MODEL") or "llama3.2:latest"
    logger.info("Configuring OllamaAdapter (model=%s)", ollama_model)
    return OllamaAdapter(base_url=ollama_base_url, model=ollama_model)
