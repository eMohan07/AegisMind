from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_github.connector import GitHubConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for github connector."""
    return GitHubConnector(config=config)


__all__ = [
    "GitHubConnector",
    "get_connector",
]
