from __future__ import annotations

from aegismind_infra.storage.memory import MemoryObjectStore
from aegismind_infra.storage.s3 import S3CompatibleObjectStore

__all__ = [
    "MemoryObjectStore",
    "S3CompatibleObjectStore",
]
