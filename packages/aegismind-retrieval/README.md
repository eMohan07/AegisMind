# aegismind-retrieval

Hybrid retrieval engine implementing dense and sparse search, Reciprocal Rank Fusion (RRF), and Zanzibar document-level access control enforcement.

## Features
- **The Sacred Enforcement Pipeline**:
  1. Embed query.
  2. Vector search with coarse tenant and group pre-filter.
  3. Overfetch by factor of 3 to 5.
  4. Call `authz.bulk_check` with consistency `at_least_as_fresh`.
  5. Keep strictly allowed documents (drop denied candidates).
  6. Rerank allowed candidates.
  7. Attach deep-linked citations.
- **Reciprocal Rank Fusion**: $k=60$ constant merging dense semantic similarity and sparse BM25/SPLADE lexical scores.
- **Vector Adapters**:
  - `MemoryVectorStoreAdapter`: In-memory vector store with cosine and sparse dot product calculation.
  - `PgVectorScaleAdapter`: PostgreSQL adapter with pgvector and pgvectorscale StreamingDiskANN index.
  - `QdrantVectorStoreAdapter`: Qdrant REST client adapter.
- **Model Adapters**:
  - `TeiEmbedderAdapter`: Text Embeddings Inference (`bge-m3`).
  - `TeiRerankerAdapter`: Text Embeddings Inference cross-encoder reranker (`bge-reranker-v2-m3`).
