from __future__ import annotations

import httpx
import pytest
import respx
from aegismind_infra.storage.memory import MemoryObjectStore
from aegismind_infra.storage.s3 import S3CompatibleObjectStore


@pytest.mark.asyncio
async def test_memory_object_store_crud_and_tenancy() -> None:
    store = MemoryObjectStore()

    # Put object with tenant
    uri = await store.put_object(
        key="docs/report.pdf",
        data=b"%PDF-sample-content",
        content_type="application/pdf",
        metadata={"author": "alice"},
        tenant_id="tenant_1",
    )
    assert uri == "memory://tenant_1/docs/report.pdf"

    # Exists and get
    assert await store.exists("docs/report.pdf", tenant_id="tenant_1") is True
    assert await store.exists("docs/report.pdf", tenant_id="tenant_2") is False

    data = await store.get_object("docs/report.pdf", tenant_id="tenant_1")
    assert data == b"%PDF-sample-content"
    assert await store.get_object("docs/report.pdf", tenant_id="tenant_2") is None

    # List objects
    keys = await store.list_objects(prefix="docs", tenant_id="tenant_1")
    assert keys == ["docs/report.pdf"]
    assert await store.list_objects(prefix="docs", tenant_id="tenant_2") == []

    # Delete object
    assert await store.delete_object("docs/report.pdf", tenant_id="tenant_1") is True
    assert await store.exists("docs/report.pdf", tenant_id="tenant_1") is False


@pytest.mark.asyncio
@respx.mock
async def test_s3_compatible_object_store_operations() -> None:
    endpoint = "http://garage.local:9000"
    bucket = "test-bucket"

    respx.put(f"{endpoint}/{bucket}/tenant_x/data.bin").mock(
        return_value=httpx.Response(200, headers={"etag": '"abcd"'})
    )
    respx.get(f"{endpoint}/{bucket}/tenant_x/data.bin").mock(
        return_value=httpx.Response(200, content=b"payload-bytes")
    )
    respx.head(f"{endpoint}/{bucket}/tenant_x/data.bin").mock(return_value=httpx.Response(200))
    respx.delete(f"{endpoint}/{bucket}/tenant_x/data.bin").mock(return_value=httpx.Response(204))

    store = S3CompatibleObjectStore(
        endpoint_url=endpoint,
        bucket=bucket,
        access_key_id="minio_key",
        secret_access_key="minio_secret",
    )

    # Put
    uri = await store.put_object("data.bin", b"payload-bytes", tenant_id="tenant_x")
    assert uri == "s3://test-bucket/tenant_x/data.bin"

    # Exists
    assert await store.exists("data.bin", tenant_id="tenant_x") is True

    # Get
    content = await store.get_object("data.bin", tenant_id="tenant_x")
    assert content == b"payload-bytes"

    # Delete
    deleted = await store.delete_object("data.bin", tenant_id="tenant_x")
    assert deleted is True
