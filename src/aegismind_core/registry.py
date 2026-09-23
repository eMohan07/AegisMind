from __future__ import annotations

import importlib.metadata
import logging
from typing import Any

logger = logging.getLogger(__name__)

# In-memory registry fallback and overrides
_REGISTRY_OVERRIDES: dict[str, dict[str, type[Any]]] = {}


def register_adapter[T](group: str, name: str, adapter_cls: type[T]) -> None:
    """Manually register an adapter class in the registry.

    This is useful for runtime configuration, custom plugins, or tests.
    """
    normalized_group = _normalize_group(group)
    if normalized_group not in _REGISTRY_OVERRIDES:
        _REGISTRY_OVERRIDES[normalized_group] = {}
    _REGISTRY_OVERRIDES[normalized_group][name] = adapter_cls
    logger.debug("Registered adapter '%s' under group '%s'", name, normalized_group)


def clear_registry_overrides() -> None:
    """Clear all manual adapter overrides."""
    _REGISTRY_OVERRIDES.clear()


def list_adapters(group: str) -> list[str]:
    """List available adapter names for a given group.

    Discovers adapters from both Python entry points and registered overrides.
    """
    normalized_group = _normalize_group(group)
    names: set[str] = set()

    # Discover from registered overrides
    if normalized_group in _REGISTRY_OVERRIDES:
        names.update(_REGISTRY_OVERRIDES[normalized_group].keys())

    # Discover from Python entry points
    try:
        eps = importlib.metadata.entry_points(group=normalized_group)
        for ep in eps:
            names.add(ep.name)
    except Exception as exc:
        logger.warning("Failed reading entry points for group '%s': %s", normalized_group, exc)

    return sorted(names)


def resolve_adapter(group: str, name: str) -> type[Any]:
    """Resolve an adapter class by group and name.

    Resolution checks explicit runtime overrides first, followed by
    standard Python entry points matching 'aegismind.<group>'.
    """
    normalized_group = _normalize_group(group)

    # 1. Check overrides
    if normalized_group in _REGISTRY_OVERRIDES and name in _REGISTRY_OVERRIDES[normalized_group]:
        logger.debug(
            "Resolved adapter '%s' for group '%s' from runtime registry",
            name,
            normalized_group,
        )
        return _REGISTRY_OVERRIDES[normalized_group][name]

    # 2. Check entry points
    try:
        eps = importlib.metadata.entry_points(group=normalized_group)
        for ep in eps:
            if ep.name == name:
                loaded_cls = ep.load()
                logger.debug(
                    "Resolved adapter '%s' for group '%s' from entry points",
                    name,
                    normalized_group,
                )
                return loaded_cls
    except Exception as exc:
        logger.error(
            "Error loading entry point for group '%s', name '%s': %s",
            normalized_group,
            name,
            exc,
        )
        raise RuntimeError(
            f"Failed to load adapter '{name}' for group '{normalized_group}'"
        ) from exc

    available = list_adapters(normalized_group)
    raise KeyError(
        f"Adapter '{name}' not found for group '{normalized_group}'. "
        f"Available adapters: {available}"
    )


def _normalize_group(group: str) -> str:
    """Normalize entry point group name to ensure 'aegismind.' prefix."""
    if group.startswith("aegismind."):
        return group
    return f"aegismind.{group}"
