"""initial raw layer

Revision ID: 001_initial_raw
Revises:
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_raw"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _raw_table(name: str, unique_name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("source_table", sa.String(length=32), nullable=False),
        sa.Column("source_key", sa.String(length=512), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_sheet", sa.String(length=64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value_states", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_version_id", "source_key", name=unique_name),
    )
    op.create_index(f"ix_{name}_dataset_version_id", name, ["dataset_version_id"])


def upgrade() -> None:
    op.create_table(
        "dataset_version",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("expected_row_count", sa.Integer(), nullable=False),
        sa.Column("actual_row_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )

    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("row_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_version.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    _raw_table("raw_bond_kr", "uq_raw_bond_kr_version_key")
    _raw_table("raw_etf_kr", "uq_raw_etf_kr_version_key")
    _raw_table("raw_etf_global", "uq_raw_etf_global_version_key")
    _raw_table("raw_fund", "uq_raw_fund_version_key")


def downgrade() -> None:
    op.drop_table("raw_fund")
    op.drop_table("raw_etf_global")
    op.drop_table("raw_etf_kr")
    op.drop_table("raw_bond_kr")
    op.drop_table("ingestion_run")
    op.drop_table("dataset_version")
