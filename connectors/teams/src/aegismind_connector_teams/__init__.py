from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_teams.connector import TeamsConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for teams connector."""
    return TeamsConnector(config=config)


__all__ = [
    "TeamsConnector",
    "get_connector",
]
