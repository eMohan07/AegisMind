from __future__ import annotations

from aegismind_connector_local_filesystem.connector import LocalFilesystemConnector


def get_connector() -> LocalFilesystemConnector:
    return LocalFilesystemConnector()


__all__ = ["LocalFilesystemConnector", "get_connector"]
