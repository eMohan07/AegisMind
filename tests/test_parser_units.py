from __future__ import annotations

import httpx
import pytest
import respx
from aegismind_ingestion.adapters_parser import (
    DoclingParserAdapter,
    MarkdownParserAdapter,
    TextParserAdapter,
)
from aegismind_types import ACL, Record


@pytest.mark.asyncio
async def test_text_parser_units() -> None:
    parser = TextParserAdapter()

    # Case 1: Standard text with title
    record1 = Record(
        id="rec_1",
        source="notes",
        external_id="ext_1",
        payload={"title": "Custom Title", "text": "Some plain content"},
    )
    doc1 = await parser.parse(record1)
    assert doc1.title == "Custom Title"
    assert doc1.content == "Some plain content"
    assert doc1.mime_type == "text/plain"

    # Case 2: Title inferred from first line
    record2 = Record(
        id="rec_2",
        source="notes",
        external_id="ext_2",
        payload={"content": "First Line Headline\nSecond line details."},
    )
    doc2 = await parser.parse(record2)
    assert doc2.title == "First Line Headline"


@pytest.mark.asyncio
async def test_markdown_parser_units() -> None:
    parser = MarkdownParserAdapter()

    # Case 1: Markdown with H1
    record = Record(
        id="rec_h1",
        source="wiki",
        external_id="w_1",
        payload={"markdown": "# User Guide\nWelcome to the platform documentation."},
    )
    doc = await parser.parse(record)
    assert doc.title == "User Guide"
    assert "Welcome" in doc.content

    # Case 2: Markdown with YAML frontmatter overriding title
    record_fm = Record(
        id="rec_fm",
        source="wiki",
        external_id="w_2",
        payload={
            "content": (
                """---
title: 'Official Guide'
version: '2.0'
---
# Ignored Header
Body text."""
            ),
        },
    )
    doc_fm = await parser.parse(record_fm)
    assert doc_fm.title == "Official Guide"
    assert doc_fm.metadata["version"] == "2.0"
    assert "# Ignored Header" in doc_fm.content


@pytest.mark.asyncio
@respx.mock
async def test_docling_parser_remote_conversion() -> None:
    endpoint = "http://docling.local:8080"
    respx.post(f"{endpoint}/v1/convert").mock(
        return_value=httpx.Response(
            200,
            json={
                "markdown": "# Converted PDF\nExtracted PDF structured content.",
                "title": "Converted PDF Document",
            },
        )
    )

    parser = DoclingParserAdapter(endpoint_url=endpoint)
    record = Record(
        id="pdf_rec",
        source="s3",
        external_id="s3://bucket/manual.pdf",
        payload={
            "file_bytes": b"%PDF-dummy-content",
            "tenant_id": "tenant_rnd",
        },
        acl=ACL(allowed_principals=["researchers"]),
    )

    doc = await parser.parse(record)
    assert doc.title == "Converted PDF Document"
    assert "Extracted PDF" in doc.content
    assert doc.metadata["parser"] == "docling"
    assert doc.tenant_id == "tenant_rnd"
