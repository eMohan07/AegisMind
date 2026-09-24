from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from aegismind_infra.ports import ObjectStorePort

logger = logging.getLogger(__name__)


class S3CompatibleObjectStore(ObjectStorePort):
    """S3-compatible object store adapter supporting AWS S3, Garage, SeaweedFS, and MinIO."""

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:9000",
        bucket: str = "aegismind-documents",
        access_key_id: str = "",
        secret_access_key: str = "",
        region: str = "us-east-1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.bucket = bucket.strip("/")
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self._client = client

    def _resolve_path(self, key: str, tenant_id: str | None) -> str:
        clean_key = key.lstrip("/")
        if tenant_id:
            return f"{tenant_id}/{clean_key}"
        return clean_key

    def _build_url(self, key: str, tenant_id: str | None) -> str:
        path = self._resolve_path(key, tenant_id)
        encoded_path = quote(path)
        return f"{self.endpoint_url}/{self.bucket}/{encoded_path}"

    def _sign_headers(
        self,
        method: str,
        url: str,
        data: bytes = b"",
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Generate AWS SigV4 authorization headers."""
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        payload_hash = hashlib.sha256(data).hexdigest()

        headers = {
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "Content-Type": content_type,
        }

        if metadata:
            for k, v in metadata.items():
                headers[f"x-amz-meta-{k.lower()}"] = v

        if not self.access_key_id or not self.secret_access_key:
            return headers

        # Calculate SigV4 signature
        canonical_uri = quote(url.replace(self.endpoint_url, "").split("?")[0])
        canonical_headers = (
            f"content-type:{content_type}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-type;x-amz-content-sha256;x-amz-date"
        canonical_request = (
            f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = (
            f"{algorithm}\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        def _sign(key_bytes: bytes, msg: str) -> bytes:
            return hmac.new(key_bytes, msg.encode("utf-8"), hashlib.sha256).digest()

        k_date = _sign(("AWS4" + self.secret_access_key).encode("utf-8"), date_stamp)
        k_region = _sign(k_date, self.region)
        k_service = _sign(k_region, "s3")
        k_signing = _sign(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        auth_header = (
            f"{algorithm} Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers["Authorization"] = auth_header
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient()

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """Store an object in S3 / Garage / SeaweedFS."""
        url = self._build_url(key, tenant_id)
        headers = self._sign_headers("PUT", url, data, content_type, metadata)

        client = await self._get_client()
        try:
            resp = await client.put(url, content=data, headers=headers)
            resp.raise_for_status()
            return f"s3://{self.bucket}/{self._resolve_path(key, tenant_id)}"
        finally:
            if self._client is None:
                await client.aclose()

    async def get_object(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bytes | None:
        """Retrieve object bytes from S3."""
        url = self._build_url(key, tenant_id)
        headers = self._sign_headers("GET", url)

        client = await self._get_client()
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content
        finally:
            if self._client is None:
                await client.aclose()

    async def delete_object(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Delete an object from S3."""
        url = self._build_url(key, tenant_id)
        headers = self._sign_headers("DELETE", url)

        client = await self._get_client()
        try:
            resp = await client.delete(url, headers=headers)
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            return True
        finally:
            if self._client is None:
                await client.aclose()

    async def exists(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Check if an object exists via HEAD request."""
        url = self._build_url(key, tenant_id)
        headers = self._sign_headers("HEAD", url)

        client = await self._get_client()
        try:
            resp = await client.head(url, headers=headers)
            return resp.status_code == 200
        finally:
            if self._client is None:
                await client.aclose()

    async def list_objects(
        self,
        prefix: str = "",
        tenant_id: str | None = None,
    ) -> list[str]:
        """List object keys using S3 ListObjectsV2 API."""
        full_prefix = self._resolve_path(prefix, tenant_id)
        url = f"{self.endpoint_url}/{self.bucket}?list-type=2&prefix={quote(full_prefix)}"
        headers = self._sign_headers("GET", url)

        client = await self._get_client()
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            # Simple XML key extraction
            text = resp.text
            import re

            keys = re.findall(r"<Key>(.*?)</Key>", text)
            if tenant_id:
                # Strip tenant prefix from returned keys
                tenant_prefix = f"{tenant_id}/"
                return [k[len(tenant_prefix) :] if k.startswith(tenant_prefix) else k for k in keys]
            return keys
        finally:
            if self._client is None:
                await client.aclose()
