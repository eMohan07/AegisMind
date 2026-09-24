from __future__ import annotations

import logging
import re
from typing import Any

from aegismind_types import Chunk, Document

from aegismind_ingestion.ports import ChunkerPort

logger = logging.getLogger(__name__)


class ContextualRetrievalGenerator:
    """Generates contextual document and section headers to enhance retrieval precision."""

    def __init__(self, max_summary_chars: int = 250) -> None:
        self.max_summary_chars = max_summary_chars

    def generate_context_prefix(
        self,
        document: Document,
        section_hierarchy: list[str],
    ) -> str:
        """Create synthesized context summary string for a chunk."""
        # Synthesize concise document overview from title and first paragraph
        content_preview = document.content.strip().split("\n\n")[0]
        summary = content_preview[: self.max_summary_chars].strip()
        if len(content_preview) > self.max_summary_chars:
            summary += "..."

        section_str = " > ".join(section_hierarchy) if section_hierarchy else "General"
        return f"Document: {document.title}\nSection: {section_str}\nContext: {summary}\n\n"


class SectionAwareChunker(ChunkerPort):
    """Section- and layout-aware chunker preserving headings, tables, and hierarchical metadata."""

    def __init__(
        self,
        max_chunk_size: int = 800,
        chunk_overlap: int = 100,
        enable_contextual_prefix: bool = True,
    ) -> None:
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.enable_contextual_prefix = enable_contextual_prefix
        self.contextual_generator = ContextualRetrievalGenerator()

    def chunk(self, document: Document) -> list[Chunk]:
        """Segment a Document into layout-aware, contextualized chunks."""
        raw_text = document.content
        if not raw_text.strip():
            return []

        lines = raw_text.splitlines()
        blocks: list[dict[str, Any]] = []

        current_hierarchy: dict[int, str] = {}
        active_block_lines: list[str] = []
        in_code_block = False
        in_table = False

        for line in lines:
            trimmed = line.strip()

            # 1. Code block boundary detection
            if trimmed.startswith("```"):
                in_code_block = not in_code_block
                active_block_lines.append(line)
                continue

            if in_code_block:
                active_block_lines.append(line)
                continue

            # 2. Table detection
            is_table_line = trimmed.startswith("|") and trimmed.endswith("|")
            if is_table_line:
                if not in_table:
                    # Flush previous paragraph before starting table
                    if active_block_lines:
                        blocks.append(
                            {
                                "lines": list(active_block_lines),
                                "hierarchy": self._current_hierarchy_list(current_hierarchy),
                                "is_table": False,
                            }
                        )
                        active_block_lines.clear()
                    in_table = True
                active_block_lines.append(line)
                continue
            elif in_table:
                # Table ended
                blocks.append(
                    {
                        "lines": list(active_block_lines),
                        "hierarchy": self._current_hierarchy_list(current_hierarchy),
                        "is_table": True,
                    }
                )
                active_block_lines.clear()
                in_table = False

            # 3. Heading detection (# H1, ## H2, etc.)
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", trimmed)
            if heading_match:
                # Flush existing content
                if active_block_lines:
                    blocks.append(
                        {
                            "lines": list(active_block_lines),
                            "hierarchy": self._current_hierarchy_list(current_hierarchy),
                            "is_table": False,
                        }
                    )
                    active_block_lines.clear()

                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # Clear deeper hierarchy levels
                current_hierarchy = {k: v for k, v in current_hierarchy.items() if k < level}
                current_hierarchy[level] = title
                active_block_lines.append(line)
                continue

            # 4. Standard text line
            if not trimmed:
                # Empty line: potential paragraph break
                if active_block_lines and len("\n".join(active_block_lines)) >= self.max_chunk_size:
                    blocks.append(
                        {
                            "lines": list(active_block_lines),
                            "hierarchy": self._current_hierarchy_list(current_hierarchy),
                            "is_table": False,
                        }
                    )
                    active_block_lines.clear()
                else:
                    active_block_lines.append(line)
            else:
                active_block_lines.append(line)

        # Flush trailing block
        if active_block_lines:
            blocks.append(
                {
                    "lines": list(active_block_lines),
                    "hierarchy": self._current_hierarchy_list(current_hierarchy),
                    "is_table": in_table,
                }
            )

        # Combine blocks into chunks honoring max_chunk_size and layout
        chunks: list[Chunk] = []
        chunk_index = 0

        current_chunk_text = ""
        current_chunk_hierarchy: list[str] = []
        current_has_table = False
        current_has_code = False

        for b in blocks:
            block_text = "\n".join(b["lines"]).strip()
            if not block_text:
                continue

            block_hierarchy = b["hierarchy"]
            block_is_table = b["is_table"]
            block_has_code = "```" in block_text

            # If adding block exceeds max_chunk_size and we already have content, finalize chunk
            if current_chunk_text and (
                len(current_chunk_text) + len(block_text) > self.max_chunk_size
            ):
                chunk_obj = self._build_chunk(
                    document=document,
                    index=chunk_index,
                    content=current_chunk_text,
                    hierarchy=current_chunk_hierarchy,
                    has_table=current_has_table,
                    has_code=current_has_code,
                )
                chunks.append(chunk_obj)
                chunk_index += 1

                # Carry over overlap if possible
                overlap_text = (
                    current_chunk_text[-self.chunk_overlap :] if self.chunk_overlap > 0 else ""
                )
                current_chunk_text = (overlap_text + "\n" + block_text).strip()
                current_chunk_hierarchy = block_hierarchy
                current_has_table = block_is_table
                current_has_code = block_has_code
            else:
                if current_chunk_text:
                    current_chunk_text += "\n\n" + block_text
                else:
                    current_chunk_text = block_text
                    current_chunk_hierarchy = block_hierarchy

                if block_is_table:
                    current_has_table = True
                if block_has_code:
                    current_has_code = True

        # Final chunk
        if current_chunk_text.strip():
            chunk_obj = self._build_chunk(
                document=document,
                index=chunk_index,
                content=current_chunk_text,
                hierarchy=current_chunk_hierarchy,
                has_table=current_has_table,
                has_code=current_has_code,
            )
            chunks.append(chunk_obj)

        return chunks

    def _current_hierarchy_list(self, hierarchy_map: dict[int, str]) -> list[str]:
        return [hierarchy_map[lvl] for lvl in sorted(hierarchy_map.keys())]

    def _build_chunk(
        self,
        document: Document,
        index: int,
        content: str,
        hierarchy: list[str],
        has_table: bool,
        has_code: bool,
    ) -> Chunk:
        context_prefix = (
            self.contextual_generator.generate_context_prefix(document, hierarchy)
            if self.enable_contextual_prefix
            else None
        )

        metadata: dict[str, Any] = {
            **document.metadata,
            "title": document.title,
            "uri": document.uri,
            "tenant_id": document.tenant_id,
            "headings": hierarchy,
            "section_path": " > ".join(hierarchy) if hierarchy else "",
            "has_table": has_table,
            "has_code": has_code,
        }

        return Chunk(
            id=f"{document.id}_chunk_{index}",
            document_id=document.id,
            index=index,
            content=content,
            contextual_prefix=context_prefix,
            acl=document.acl,
            metadata=metadata,
        )
