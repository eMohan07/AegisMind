from __future__ import annotations

import pytest

from aegismind_core.registry import (
    clear_registry_overrides,
    list_adapters,
    register_adapter,
    resolve_adapter,
)


def test_list_and_resolve_entry_point_adapters() -> None:
    authz_adapters = list_adapters("authz")
    assert "memory" in authz_adapters
    assert "spicedb" in authz_adapters

    vector_adapters = list_adapters("vector_store")
    assert "memory" in vector_adapters

    adapter_cls = resolve_adapter("authz", "memory")
    assert adapter_cls.__name__ == "MemoryAuthzAdapter"


def test_runtime_adapter_override() -> None:
    class CustomAuthzAdapter:
        pass

    try:
        register_adapter("authz", "custom", CustomAuthzAdapter)
        assert "custom" in list_adapters("authz")

        resolved = resolve_adapter("authz", "custom")
        assert resolved is CustomAuthzAdapter
    finally:
        clear_registry_overrides()


def test_resolve_unknown_adapter_raises() -> None:
    with pytest.raises(KeyError) as exc_info:
        resolve_adapter("authz", "nonexistent_adapter_xyz")
    assert "nonexistent_adapter_xyz" in str(exc_info.value)
