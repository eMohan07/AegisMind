"""Initial schema for AegisMind relational and vector tables

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-09-25 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Initialize PostgreSQL extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Table: aegismind_envelopes
    op.create_table(
        "aegismind_envelopes",
        sa.Column("key_id", sa.String(length=128), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=128),
            nullable=False,
            server_default="corp-default",
        ),
        sa.Column("encrypted_dek", postgresql.BYTEA(), nullable=False),
        sa.Column("nonce", postgresql.BYTEA(), nullable=False),
        sa.Column("tag", postgresql.BYTEA(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_envelopes_tenant", "aegismind_envelopes", ["tenant_id"])

    # 3. Table: aegismind_records
    op.create_table(
        "aegismind_records",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("acl", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "tenant_id",
            sa.String(length=128),
            nullable=False,
            server_default="corp-default",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "idx_records_tenant_source",
        "aegismind_records",
        ["tenant_id", "source"],
    )

    # 4. Table: aegismind_chunks
    op.execute(
        """
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
        """
    )
    op.create_index(
        "idx_chunks_tenant_doc",
        "aegismind_chunks",
        ["tenant_id", "document_id"],
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_active
            ON aegismind_chunks(tenant_id, document_id)
            WHERE is_deleted = FALSE;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_vector_hnsw
            ON aegismind_chunks USING hnsw (dense_embedding vector_cosine_ops);
        """
    )

    # 5. Table: aegismind_ingest_queue
    op.create_table(
        "aegismind_ingest_queue",
        sa.Column("msg_id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=128),
            nullable=False,
            server_default="corp-default",
        ),
        sa.Column("read_ct", sa.Integer(), nullable=True, server_default="0"),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "vt",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("message", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("idx_ingest_queue_tenant", "aegismind_ingest_queue", ["tenant_id", "vt"])

    # 6. Table: aegismind_feedback
    op.create_table(
        "aegismind_feedback",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=128),
            nullable=False,
            server_default="corp-default",
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column(
            "retrieved_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("rating", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_feedback_tenant", "aegismind_feedback", ["tenant_id"])

    # 7. Table: aegismind_dlq
    op.create_table(
        "aegismind_dlq",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=512), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_failed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_dlq_status", "aegismind_dlq", ["status", "last_failed_at"])
    op.create_index("idx_dlq_connector", "aegismind_dlq", ["connector_id"])

    # 8. Row Level Security policies
    op.execute("ALTER TABLE aegismind_chunks ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE aegismind_records ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE aegismind_feedback ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE aegismind_dlq ENABLE ROW LEVEL SECURITY;")

    op.execute(
        """
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
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_records ON aegismind_records;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_chunks ON aegismind_chunks;")
    op.drop_table("aegismind_dlq")
    op.drop_table("aegismind_feedback")
    op.drop_table("aegismind_ingest_queue")
    op.execute("DROP TABLE IF EXISTS aegismind_chunks;")
    op.drop_table("aegismind_records")
    op.drop_table("aegismind_envelopes")
