from __future__ import annotations

import logging

from aegismind_authz.mappers import acl_to_relationship_tuples
from aegismind_authz.ports import AuthzPort
from aegismind_retrieval.ports import EmbedderPort, VectorStorePort
from aegismind_types import Chunk, Document, Record

from aegismind_ingestion.chunking import SectionAwareChunker
from aegismind_ingestion.ports import (
    ChunkerPort,
    IngestionPipelinePort,
    IngestionSummary,
    ParserPort,
)

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
    ) -> None:
        self.parser = parser
        self.vector_store = vector_store
        self.embedder = embedder
        self.authz = authz
        self.chunker = chunker or SectionAwareChunker()

    async def ingest_records(self, records: list[Record]) -> IngestionSummary:
        """Process a batch of raw records through the ingestion lifecycle.

        Stages:
        1. Parsing raw records to canonical Documents.
        2. Section-aware layout chunking with contextual prefixes.
        3. Dense embedding generation.
        4. Vector store indexing.
        5. Zanzibar relationship tuple mapping and write to Authz.
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

        # 2. Chunk documents
        for doc in documents:
            try:
                doc_chunks = self.chunker.chunk(doc)
                all_chunks.extend(doc_chunks)
            except Exception as exc:
                err_msg = f"Failed to chunk document {doc.id}: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)

        # 3. Embed chunks
        if all_chunks:
            chunk_texts = [
                f"{c.contextual_prefix}{c.content}" if c.contextual_prefix else c.content
                for c in all_chunks
            ]
            try:
                embeddings = await self.embedder.embed_documents(chunk_texts)
                sparse_embeddings = (
                    await self.embedder.embed_sparse_documents(chunk_texts)
                    if hasattr(self.embedder, "embed_sparse_documents")
                    else [None] * len(all_chunks)
                )
                embedded_chunks: list[Chunk] = []
                for chunk, emb, sparse_emb in zip(
                    all_chunks, embeddings, sparse_embeddings, strict=False
                ):
                    # Attach generated dense and sparse vector representations
                    updated_chunk = Chunk(
                        id=chunk.id,
                        document_id=chunk.document_id,
                        index=chunk.index,
                        content=chunk.content,
                        contextual_prefix=chunk.contextual_prefix,
                        embedding=emb,
                        sparse_embedding=sparse_emb or chunk.sparse_embedding,
                        acl=chunk.acl,
                        metadata=chunk.metadata,
                    )
                    embedded_chunks.append(updated_chunk)

                # 4. Upsert into vector store
                await self.vector_store.upsert(embedded_chunks)
            except Exception as exc:
                err_msg = f"Failed during embedding / vector store indexing: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)

        # 5. Map ACLs to Zanzibar relationship tuples and write to Authz
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

        return IngestionSummary(
            records_ingested=total_records,
            documents_created=len(documents),
            chunks_indexed=len(all_chunks),
            tuples_written=len(all_tuples),
            errors=errors,
        )
