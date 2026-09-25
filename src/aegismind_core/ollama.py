from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")


def get_candidate_ollama_urls() -> list[str]:
    """Get list of candidate Ollama URLs in priority order."""
    env_url = os.environ.get("OLLAMA_URL")
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
    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


async def find_active_ollama_url() -> str | None:
    """Find the first responsive Ollama endpoint."""
    candidates = get_candidate_ollama_urls()
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


async def list_available_models(base_url: str | None = None) -> list[str]:
    """List available LLM models from Ollama."""
    url = base_url or await find_active_ollama_url()
    if not url:
        return []

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return models
    except Exception as exc:
        logger.debug("Failed listing Ollama models: %s", exc)
    return []


async def stream_ollama_completion(
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> AsyncIterator[str]:
    """Stream completion tokens from Ollama."""
    active_url = base_url or await find_active_ollama_url()
    if not active_url:
        return

    chosen_model = model or DEFAULT_OLLAMA_MODEL

    payload: dict[str, Any] = {
        "model": chosen_model,
        "prompt": prompt,
        "stream": True,
    }
    if system_prompt:
        payload["system"] = system_prompt

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", f"{active_url}/api/generate", json=payload) as response:
            if response.status_code != 200:
                logger.warning("Ollama returned status %d", response.status_code)
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
