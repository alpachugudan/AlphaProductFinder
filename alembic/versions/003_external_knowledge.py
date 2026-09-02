"""external knowledge layer

Revision ID: 003_external_knowledge
Revises: 002_curated_layer
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "003_external_knowledge"
down_revision: str | None = "002_curated_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_ingestion_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manifest_hash"),
    )

    op.create_table(
        "source_document",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("effective_as_of", sa.Date(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("local_path", sa.String(length=1024), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("authority_rank", sa.Integer(), nullable=False),
        sa.Column("usage_note", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id"),
    )

    op.create_table(
        "entity",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=512), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column(
            "identifiers_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id"),
    )

    op.create_table(
        "entity_alias",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alias", sa.String(length=512), nullable=False),
        sa.Column("normalized_alias", sa.String(length=512), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("alias_type", sa.String(length=64), nullable=False),
        sa.Column("source_document_id", sa.String(length=128), nullable=False),
        sa.Column("match_method", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.entity_id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_document.document_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_alias", "entity_id", name="uq_entity_alias_norm_entity"),
    )
    op.create_index("ix_entity_alias_normalized_alias", "entity_alias", ["normalized_alias"])

    op.create_table(
        "product_holding",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_uid", sa.String(length=128), nullable=False),
        sa.Column("holding_entity_id", sa.String(length=128), nullable=False),
        sa.Column("holding_name_raw", sa.String(length=512), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("weight_unit", sa.String(length=32), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("source_document_id", sa.String(length=128), nullable=False),
        sa.Column(
            "quality_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("coverage_status", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["holding_entity_id"], ["entity.entity_id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_document.document_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_holding_product_uid", "product_holding", ["product_uid"])
    op.create_index(
        "ix_product_holding_holding_entity_id", "product_holding", ["holding_entity_id"]
    )

    op.create_table(
        "entity_relation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("subject_entity_id", sa.String(length=128), nullable=False),
        sa.Column("object_entity_id", sa.String(length=128), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_document_id", sa.String(length=128), nullable=False),
        sa.Column("confidence_basis", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column(
            "quality_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["object_entity_id"], ["entity.entity_id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_document.document_id"]),
        sa.ForeignKeyConstraint(["subject_entity_id"], ["entity.entity_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entity_relation_subject", "entity_relation", ["subject_entity_id"])
    op.create_index("ix_entity_relation_object", "entity_relation", ["object_entity_id"])

    op.create_table(
        "document_chunk",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chunk_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=128), nullable=False),
        sa.Column(
            "entity_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_version", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["source_document.document_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id"),
    )


def downgrade() -> None:
    op.drop_table("document_chunk")
    op.drop_table("entity_relation")
    op.drop_table("product_holding")
    op.drop_table("entity_alias")
    op.drop_table("entity")
    op.drop_table("source_document")
    op.drop_table("external_ingestion_run")
