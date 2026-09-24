from __future__ import annotations

import pytest
from aegismind_ingestion.adapters_parser import (
    DoclingParserAdapter,
    MarkdownParserAdapter,
    TextParserAdapter,
)
from aegismind_ingestion.chunking import ContextualRetrievalGenerator, SectionAwareChunker
from aegismind_types import ACL, Document, Record


def test_contextual_retrieval_generator() -> None:
    doc = Document(
        id="doc_test",
        title="Distributed Systems Architecture",
        content=(
            "This document details the consensus protocol and partition tolerance guarantees.\n\n"
            "More details follow..."
        ),
    )
    generator = ContextualRetrievalGenerator()
    prefix = generator.generate_context_prefix(doc, ["Architecture", "Consensus"])

    assert "Document: Distributed Systems Architecture" in prefix
    assert "Section: Architecture > Consensus" in prefix
    assert "Context: This document details the consensus protocol" in prefix


def test_section_aware_chunking_with_headings_and_tables() -> None:
    markdown_content = """# Architecture Overview
This is the root architecture document.

## Storage Engine
Details on LSM tree storage.

| Component | Technology | Throughput |
| --- | --- | --- |
| Cache | Redis | 100k ops/sec |
| Storage | RocksDB | 50k ops/sec |

### Compaction Strategy
Leveled compaction is used for read efficiency.

```python
def compact():
    pass
```
"""

    doc = Document(
        id="doc_arch",
        title="Architecture Overview",
        content=markdown_content,
        acl=ACL(allowed_principals=["engineering"]),
    )

    chunker = SectionAwareChunker(max_chunk_size=300, chunk_overlap=30)
    chunks = chunker.chunk(doc)

    assert len(chunks) >= 2

    # Check headings and section hierarchy preservation
    compaction_chunk = next((c for c in chunks if "Compaction Strategy" in c.content), None)
    assert compaction_chunk is not None
    assert "Architecture Overview" in compaction_chunk.metadata["headings"]
    assert "Storage Engine" in compaction_chunk.metadata["headings"]
    assert "Compaction Strategy" in compaction_chunk.metadata["headings"]
    assert compaction_chunk.metadata["has_code"] is True

    # Check table preservation
    table_chunk = next((c for c in chunks if "| Component |" in c.content), None)
    assert table_chunk is not None
    assert table_chunk.metadata["has_table"] is True
    assert "| Cache | Redis |" in table_chunk.content

    # Check contextual prefix attached
    for c in chunks:
        assert c.contextual_prefix is not None
        assert "Document: Architecture Overview" in c.contextual_prefix


@pytest.mark.asyncio
async def test_markdown_parser_with_frontmatter() -> None:
    parser = MarkdownParserAdapter()
    record = Record(
        id="rec_md_1",
        source="confluence",
        external_id="conf_99",
        payload={
            "content": (
                "---\ntitle: Security Guardrails\nauthor: alice\n---\n\n"
                "# Security Guardrails\nAccess control rules."
            ),
            "tenant_id": "tenant_prod",
        },
        acl=ACL(allowed_principals=["sec_team"]),
    )

    doc = await parser.parse(record)
    assert doc.id == "rec_md_1"
    assert doc.title == "Security Guardrails"
    assert doc.metadata["author"] == "alice"
    assert doc.tenant_id == "tenant_prod"
    assert doc.content == "# Security Guardrails\nAccess control rules."


@pytest.mark.asyncio
async def test_text_parser() -> None:
    parser = TextParserAdapter()
    record = Record(
        id="rec_txt_1",
        source="slack",
        external_id="msg_42",
        payload={
            "text": "Incident Postmortem 2026-09\nRoot cause was network partition.",
            "tenant": "acme",
        },
    )

    doc = await parser.parse(record)
    assert doc.id == "rec_txt_1"
    assert doc.title == "Incident Postmortem 2026-09"
    assert doc.tenant_id == "acme"
    assert "Root cause" in doc.content


@pytest.mark.asyncio
async def test_docling_parser_fallback() -> None:
    parser = DoclingParserAdapter()
    record = Record(
        id="rec_docling_1",
        source="upload",
        external_id="file_1",
        payload={
            "content": "# Research Paper\nDeep Learning in Information Retrieval.",
            "title": "Research Paper",
        },
    )

    doc = await parser.parse(record)
    assert doc.id == "rec_docling_1"
    assert doc.title == "Research Paper"
    assert "Deep Learning" in doc.content


@pytest.mark.asyncio
async def test_durable_workflow_engine_replayability() -> None:
    from aegismind_ingestion.workflow_dbos import DurableWorkflowEngine

    engine = DurableWorkflowEngine()
    engine.start_workflow("run_100")

    call_count = 0

    def compute(val: int) -> int:
        nonlocal call_count
        call_count += 1
        return val * 2

    # First attempt: executes step
    res1: int = await engine.execute_step("run_100", "step_double", compute, 21)
    assert res1 == 42
    assert call_count == 1

    # Second attempt (replay): retrieves from checkpoint without re-executing
    res2: int = await engine.execute_step("run_100", "step_double", compute, 21)
    assert res2 == 42
    assert call_count == 1  # Not incremented on replay!


@pytest.mark.asyncio
async def test_scribe_worker_sync() -> None:
    from collections.abc import AsyncIterator
    from typing import Any

    from aegismind_connector_sdk.ports import ConnectorSpec
    from aegismind_ingestion.ports import IngestionPipelinePort, IngestionSummary
    from aegismind_ingestion.worker import ScribeWorker

    class DummyPipeline(IngestionPipelinePort):
        async def ingest_records(self, records: list[Record]) -> IngestionSummary:
            return IngestionSummary(
                records_ingested=len(records),
                documents_created=len(records),
                chunks_indexed=len(records) * 2,
                tuples_written=len(records),
            )

    class DummyConnector:
        def spec(self) -> ConnectorSpec:
            return ConnectorSpec(name="dummy_src", version="0.1.0")

        async def check(self) -> bool:
            return True

        def read(self, state: dict[str, Any] | None = None) -> AsyncIterator[Record]:
            async def _gen() -> AsyncIterator[Record]:
                for i in range(5):
                    yield Record(
                        id=f"r_{i}",
                        source="dummy",
                        external_id=str(i),
                        payload={"content": f"Record content {i}"},
                    )

            return _gen()

    worker = ScribeWorker(pipeline=DummyPipeline(), batch_size=2)
    report = await worker.run_sync("run_scribe_1", DummyConnector())

    assert report.status == "COMPLETED"
    assert report.records_synced == 5
    assert report.chunks_indexed == 10
    assert report.tuples_written == 5
    assert report.final_cursor["last_record_id"] == "r_4"
