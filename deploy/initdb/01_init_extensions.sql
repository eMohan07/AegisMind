-- AegisMind: PostgreSQL 17 Database Initialization
-- Initializes required extensions for vector search and durable queueing.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- Initialize pgvectorscale if available
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'vectorscale extension not available in this container image, falling back to standard pgvector HNSW.';
END $$;

-- Initialize pgmq if available
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pgmq CASCADE;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgmq extension not available in this container image, queue tables will be created in schema.';
END $$;
