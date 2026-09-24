from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from aegismind_types import Document, Record

from aegismind_ingestion.ports import ParserPort

logger = logging.getLogger(__name__)


class TextParserAdapter(ParserPort):
    """Parser for raw plaintext records."""

    async def parse(self, record: Record) -> Document:
        payload = record.payload
        content = (
            payload.get("content") or payload.get("text") or payload.get("body") or str(payload)
        )
        content_str = str(content).strip()

        # Derive title from metadata or first line of text
        title = (
            payload.get("title")
            or payload.get("name")
            or (content_str.splitlines()[0][:80] if content_str else f"Record {record.id}")
        )

        uri = payload.get("uri") or payload.get("url")
        tenant_id = payload.get("tenant_id") or payload.get("tenant")

        return Document(
            id=record.id,
            uri=str(uri) if uri else None,
            title=str(title),
            mime_type="text/plain",
            content=content_str,
            metadata=dict(payload),
            acl=record.acl,
            tenant_id=str(tenant_id) if tenant_id else None,
        )


class MarkdownParserAdapter(ParserPort):
    """Parser for Markdown documents with frontmatter and heading extraction."""

    async def parse(self, record: Record) -> Document:
        payload = record.payload
        raw_text = str(
            payload.get("content") or payload.get("text") or payload.get("markdown") or str(payload)
        ).strip()

        metadata: dict[str, Any] = dict(payload)
        body = raw_text

        # Extract YAML frontmatter if present (--- ... ---)
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw_text, re.DOTALL)
        if frontmatter_match:
            frontmatter_raw = frontmatter_match.group(1)
            body = frontmatter_match.group(2).strip()
            # Simple key: value extraction
            for line in frontmatter_raw.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    metadata[k.strip()] = v.strip().strip('"').strip("'")

        # Extract title from # Heading or metadata
        title = metadata.get("title")
        if not title:
            h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if h1_match:
                title = h1_match.group(1).strip()
            else:
                title = f"Document {record.id}"

        uri = metadata.get("uri") or metadata.get("url")
        tenant_id = metadata.get("tenant_id") or metadata.get("tenant")

        return Document(
            id=record.id,
            uri=str(uri) if uri else None,
            title=str(title),
            mime_type="text/markdown",
            content=body,
            metadata=metadata,
            acl=record.acl,
            tenant_id=str(tenant_id) if tenant_id else None,
        )


class DoclingParserAdapter(ParserPort):
    """Docling document parser adapter for multi-format complex layout documents."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/") if endpoint_url else None
        self._client = client
        self._fallback_md = MarkdownParserAdapter()

    async def parse(self, record: Record) -> Document:
        payload = record.payload

        # If remote Docling service configured and document bytes available
        if self.endpoint_url and "file_bytes" in payload:
            try:
                client = self._client or httpx.AsyncClient()
                files = {"file": payload["file_bytes"]}
                resp = await client.post(f"{self.endpoint_url}/v1/convert", files=files)
                resp.raise_for_status()
                result = resp.json()
                parsed_markdown = result.get("markdown", "")
                title = result.get("title", f"Document {record.id}")

                return Document(
                    id=record.id,
                    uri=payload.get("uri"),
                    title=title,
                    mime_type="text/markdown",
                    content=parsed_markdown,
                    metadata={**payload, "parser": "docling"},
                    acl=record.acl,
                    tenant_id=payload.get("tenant_id"),
                )
            except Exception as exc:
                logger.warning("Remote Docling conversion failed, falling back: %s", exc)

        # Fallback to structural markdown parser
        return await self._fallback_md.parse(record)
