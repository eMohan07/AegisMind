from __future__ import annotations

import hashlib
import logging

from aegismind_authz.mappers import acl_to_relationship_tuples
from aegismind_authz.ports import AuthzPort
from aegismind_retrieval.ports import EmbedderPort, VectorStorePort
from aegismind_types import Chunk, Document, Record

from aegismind_ingestion.chunking import SectionAwareChunker
from aegismind_ingestion.ports import (
    ChunkerPort,
    DLQPort,
    IngestionPipelinePort,
    IngestionSummary,
    ParserPort,
)
from aegismind_ingestion.sanitizer import IngestionSanitizer

logger = logging.getLogger(__name__)


class IngestionPipeline(IngestionPipelinePort):
    """End-to-end ingestion pipeline coordinating parsing, chunking, embedding, and authz."""

    def __init__(
        self,
        parser: ParserPort,
        vector_store: VectorStorePort,
        embedder: EmbedderPort,
        authz: AuthzPort,
        chunker: ChunkerPort | None = None,
        sanitizer: IngestionSanitizer | None = None,
        dlq: DLQPort | None = None,
    ) -> None:
        self.parser = parser
        self.vector_store = vector_store
        self.embedder = embedder
        self.authz = authz
        self.chunker = chunker or SectionAwareChunker()
        self.sanitizer = sanitizer or IngestionSanitizer()
        self.dlq = dlq

    async def ingest_records(self, records: list[Record]) -> IngestionSummary:
        """Process a batch of raw records through the ingestion lifecycle.

        Enforces:
        1. Parse records to canonical Documents.
        2. Write Zanzibar SpiceDB relationship tuples before indexing chunks.
        3. Chunk documents, sanitize, and compute SHA-256 content hashes.
        4. Preserve existing embeddings for unchanged chunks to avoid re-embedding.
        5. Atomically soft-delete old document chunks and upsert versioned chunks.
        """
        if not records:
            return IngestionSummary()

        total_records = len(records)
        documents: list[Document] = []
        all_chunks: list[Chunk] = []
        all_tuples = []
        errors: list[str] = []

        # 1. Parse records
        for record in records:
            try:
                doc = await self.parser.parse(record)
                documents.append(doc)
            except Exception as exc:
                err_msg = f"Failed to parse record {record.id}: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)
                if self.dlq is not None:
                    try:
                        await self.dlq.enqueue(
                            connector_id=record.source or "unknown",
                            resource_id=record.id,
                            error_message=err_msg,
                            payload=record.payload if hasattr(record, "payload") else {},
                        )
                    except Exception as dlq_exc:
                        logger.warning("Failed enqueueing parse failure to DLQ: %s", dlq_exc)

        # 2. Write SpiceDB tuples first so permissions are active before chunks become searchable
        for doc in documents:
            try:
                tuples = acl_to_relationship_tuples(
                    acl=doc.acl,
                    resource_id=doc.id,
                    resource_type="document",
                )
                all_tuples.extend(tuples)
            except Exception as exc:
                err_msg = f"Failed to map ACLs for document {doc.id}: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)

        if all_tuples:
            try:
                await self.authz.write_tuples(all_tuples)
                logger.info(
                    "Wrote %d Zanzibar relationship tuples for %d documents",
                    len(all_tuples),
                    len(documents),
                )
            except Exception as exc:
                err_msg = f"Failed to write relationship tuples to Authz: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)

        # 3. Chunk documents, check SHA-256 content hashes, and identify chunks to embed
        prepared_chunks: list[Chunk] = []
        chunks_to_embed: list[tuple[Chunk, str, int]] = []

        for doc in documents:
            try:
                existing_chunks = await self.vector_store.get_by_document(doc.id)
                existing_hash_map: dict[str, Chunk] = {
                    c.content_hash: c for c in existing_chunks if c.content_hash and c.embedding
                }
                next_version = max((c.version for c in existing_chunks), default=0) + 1

                doc_chunks = self.chunker.chunk(doc)
                for c in doc_chunks:
                    san_res = self.sanitizer.sanitize(c.content, chunk_id=c.id)
                    cleaned_content = (
                        san_res.cleaned_text if san_res.stripped_patterns else c.content
                    )
                    chunk_meta = dict(c.metadata)
                    if san_res.stripped_patterns:
                        chunk_meta["sanitized_patterns"] = san_res.stripped_patterns

                    # Compute SHA-256 content hash
                    hash_input = (
                        f"{c.contextual_prefix}{cleaned_content}"
                        if c.contextual_prefix
                        else cleaned_content
                    )
                    content_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

                    # Check if unchanged chunk already has embedding in prior version
                    versioned_chunk_id = f"{c.document_id}_v{next_version}_chunk_{c.index}"
                    if content_hash in existing_hash_map:
                        cached = existing_hash_map[content_hash]
                        logger.debug(
                            "Reusing vector embedding for unchanged chunk %s (hash=%s)",
                            versioned_chunk_id,
                            content_hash,
                        )
                        reused_chunk = Chunk(
                            id=versioned_chunk_id,
                            document_id=c.document_id,
                            index=c.index,
                            content=cleaned_content,
                            contextual_prefix=c.contextual_prefix,
                            embedding=cached.embedding,
                            sparse_embedding=cached.sparse_embedding,
                            acl=c.acl,
                            metadata=chunk_meta,
                            content_hash=content_hash,
                            is_deleted=False,
                            version=next_version,
                        )
                        prepared_chunks.append(reused_chunk)
                    else:
                        pending_chunk = Chunk(
                            id=versioned_chunk_id,
                            document_id=c.document_id,
                            index=c.index,
                            content=cleaned_content,
                            contextual_prefix=c.contextual_prefix,
                            acl=c.acl,
                            metadata=chunk_meta,
                            content_hash=content_hash,
                            is_deleted=False,
                            version=next_version,
                        )
                        chunks_to_embed.append((pending_chunk, content_hash, next_version))
            except Exception as exc:
                err_msg = f"Failed chunking/versioning document {doc.id}: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)
                if self.dlq is not None:
                    try:
                        await self.dlq.enqueue(
                            connector_id=doc.metadata.get("source") or "unknown",
                            resource_id=doc.id,
                            error_message=err_msg,
                            payload={"title": doc.title, "document_id": doc.id},
                        )
                    except Exception as dlq_exc:
                        logger.warning("Failed enqueueing chunking failure to DLQ: %s", dlq_exc)

        # 4. Generate embeddings only for newly created or modified chunks
        if chunks_to_embed:
            chunk_texts = [
                f"{c.contextual_prefix}{c.content}" if c.contextual_prefix else c.content
                for c, _, _ in chunks_to_embed
            ]
            try:
                embeddings = await self.embedder.embed_documents(chunk_texts)
                sparse_embeddings = (
                    await self.embedder.embed_sparse_documents(chunk_texts)
                    if hasattr(self.embedder, "embed_sparse_documents")
                    else [None] * len(chunks_to_embed)
                )
                for (c, chash, ver), emb, sparse_emb in zip(
                    chunks_to_embed, embeddings, sparse_embeddings, strict=False
                ):
                    updated_chunk = Chunk(
                        id=c.id,
                        document_id=c.document_id,
                        index=c.index,
                        content=c.content,
                        contextual_prefix=c.contextual_prefix,
                        embedding=emb,
                        sparse_embedding=sparse_emb or c.sparse_embedding,
                        acl=c.acl,
                        metadata=c.metadata,
                        content_hash=chash,
                        is_deleted=False,
                        version=ver,
                    )
                    prepared_chunks.append(updated_chunk)
            except Exception as exc:
                err_msg = f"Failed during embedding generation: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)
                if self.dlq is not None:
                    for pending, _, _ in chunks_to_embed:
                        try:
                            await self.dlq.enqueue(
                                connector_id=pending.metadata.get("source") or "unknown",
                                resource_id=pending.id,
                                error_message=err_msg,
                                payload={
                                    "content": pending.content,
                                    "document_id": pending.document_id,
                                },
                            )
                        except Exception as dlq_exc:
                            logger.warning(
                                "Failed enqueueing embedding failure to DLQ: %s", dlq_exc
                            )

        # 5. Atomically soft-delete old document chunks and index new versioned chunks
        for doc in documents:
            try:
                await self.vector_store.soft_delete_document(doc.id)
            except Exception as exc:
                err_msg = f"Failed soft-deleting previous chunks for {doc.id}: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)

        if prepared_chunks:
            try:
                await self.vector_store.upsert(prepared_chunks)
                all_chunks.extend(prepared_chunks)
            except Exception as exc:
                err_msg = f"Failed indexing chunks into vector store: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)
                if self.dlq is not None:
                    for chunk_item in prepared_chunks:
                        try:
                            await self.dlq.enqueue(
                                connector_id=chunk_item.metadata.get("source") or "unknown",
                                resource_id=chunk_item.id,
                                error_message=err_msg,
                                payload={
                                    "content": chunk_item.content,
                                    "document_id": chunk_item.document_id,
                                },
                            )
                        except Exception as dlq_exc:
                            logger.warning("Failed enqueueing upsert failure to DLQ: %s", dlq_exc)

        return IngestionSummary(
            records_ingested=total_records,
            documents_created=len(documents),
            chunks_indexed=len(all_chunks),
            tuples_written=len(all_tuples),
            errors=errors,
        )
