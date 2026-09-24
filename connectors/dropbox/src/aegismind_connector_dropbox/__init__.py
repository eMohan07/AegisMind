from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_dropbox.connector import DropboxConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for dropbox connector."""
    return DropboxConnector(config=config)


__all__ = [
    "DropboxConnector",
    "get_connector",
]
