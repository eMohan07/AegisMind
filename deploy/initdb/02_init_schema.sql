-- AegisMind: Core relational and vector tables schema
-- Ensures tables exist for envelope encryption, records, chunks, and message queues.

CREATE TABLE IF NOT EXISTS aegismind_envelopes (
    key_id VARCHAR(128) PRIMARY KEY,
    encrypted_dek BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    tag BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rotated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS aegismind_records (
    id VARCHAR(128) PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    external_id VARCHAR(512) NOT NULL,
    payload JSONB NOT NULL,
    acl JSONB NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_records_tenant_source 
    ON aegismind_records(tenant_id, source);

CREATE TABLE IF NOT EXISTS aegismind_chunks (
    id VARCHAR(128) PRIMARY KEY,
    document_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    contextual_prefix TEXT,
    dense_embedding vector(1024),
    sparse_embedding JSONB,
    acl JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_doc 
    ON aegismind_chunks(tenant_id, document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_vector_hnsw 
    ON aegismind_chunks USING hnsw (dense_embedding vector_cosine_ops);

-- Queue table for durable ingestion jobs when pgmq native extension is absent
CREATE TABLE IF NOT EXISTS aegismind_ingest_queue (
    msg_id BIGSERIAL PRIMARY KEY,
    read_ct INT DEFAULT 0,
    enqueued_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    vt TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    message JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ingest_queue_vt 
    ON aegismind_ingest_queue(vt);
