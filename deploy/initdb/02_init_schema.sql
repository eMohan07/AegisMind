-- AegisMind: Core relational and vector tables schema
-- Ensures tables exist for envelope encryption, records, chunks, and message queues.

CREATE TABLE IF NOT EXISTS aegismind_envelopes (
    key_id VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'corp-default',
    encrypted_dek BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    tag BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rotated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_envelopes_tenant 
    ON aegismind_envelopes(tenant_id);

CREATE TABLE IF NOT EXISTS aegismind_records (
    id VARCHAR(128) PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    external_id VARCHAR(512) NOT NULL,
    payload JSONB NOT NULL,
    acl JSONB NOT NULL,
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'corp-default',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_records_tenant_source 
    ON aegismind_records(tenant_id, source);

CREATE TABLE IF NOT EXISTS aegismind_chunks (
    id VARCHAR(128) PRIMARY KEY,
    document_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'corp-default',
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    contextual_prefix TEXT,
    dense_embedding vector(1024),
    sparse_embedding JSONB,
    acl JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_hash VARCHAR(64),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_doc 
    ON aegismind_chunks(tenant_id, document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_active 
    ON aegismind_chunks(tenant_id, document_id) 
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_chunks_vector_hnsw 
    ON aegismind_chunks USING hnsw (dense_embedding vector_cosine_ops);

-- Queue table for durable ingestion jobs when pgmq native extension is absent
CREATE TABLE IF NOT EXISTS aegismind_ingest_queue (
    msg_id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'corp-default',
    read_ct INT DEFAULT 0,
    enqueued_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    vt TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    message JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ingest_queue_tenant 
    ON aegismind_ingest_queue(tenant_id, vt);

-- User feedback storage table
CREATE TABLE IF NOT EXISTS aegismind_feedback (
    id VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'corp-default',
    query TEXT NOT NULL,
    rewritten_query TEXT,
    retrieved_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    rating VARCHAR(32) NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feedback_tenant 
    ON aegismind_feedback(tenant_id);

-- PostgreSQL Row Level Security (RLS) policies for multi-tenancy defense in depth
ALTER TABLE aegismind_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE aegismind_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE aegismind_feedback ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_chunks'
    ) THEN
        CREATE POLICY tenant_isolation_chunks ON aegismind_chunks
            FOR ALL
            USING (
                tenant_id = CURRENT_SETTING('app.current_tenant', true)
                OR CURRENT_SETTING('app.current_tenant', true) = ''
                OR CURRENT_SETTING('app.current_tenant', true) IS NULL
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_records'
    ) THEN
        CREATE POLICY tenant_isolation_records ON aegismind_records
            FOR ALL
            USING (
                tenant_id = CURRENT_SETTING('app.current_tenant', true)
                OR CURRENT_SETTING('app.current_tenant', true) = ''
                OR CURRENT_SETTING('app.current_tenant', true) IS NULL
            );
    END IF;
END $$;
