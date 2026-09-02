"""curated search layer

Revision ID: 002_curated_layer
Revises: 001_initial_raw
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_curated_layer"
down_revision: str | None = "001_initial_raw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENVELOPE_COLUMNS = [
    sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column("product_uid", sa.String(length=128), nullable=False),
    sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
    sa.Column("source_table", sa.String(length=32), nullable=False),
    sa.Column("source_key", sa.String(length=512), nullable=False),
    sa.Column("raw_row_id", sa.BigInteger(), nullable=False),
    sa.Column("product_family", sa.String(length=32), nullable=False),
    sa.Column("product_name", sa.String(length=512), nullable=True),
    sa.Column("product_name_normalized", sa.String(length=512), nullable=True),
    sa.Column("manager_or_issuer_raw", sa.String(length=255), nullable=True),
    sa.Column("currency_raw", sa.String(length=32), nullable=True),
    sa.Column("market_raw", sa.String(length=64), nullable=True),
    sa.Column("asset_type_raw", sa.String(length=128), nullable=True),
    sa.Column("investment_region_raw", sa.String(length=128), nullable=True),
    sa.Column("risk_label_raw", sa.String(length=128), nullable=True),
    sa.Column("sale_status_raw", sa.String(length=64), nullable=True),
    sa.Column("primary_as_of_date", sa.Date(), nullable=True),
    sa.Column("quality_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    ),
]

SEARCH_VIEW_SQL = """
CREATE OR REPLACE VIEW product_search_view AS
SELECT
    product_uid,
    dataset_version_id,
    product_family,
    source_table,
    source_key,
    product_name,
    product_name_normalized,
    manager_or_issuer_raw,
    currency_raw,
    market_raw,
    asset_type_raw,
    investment_region_raw,
    risk_label_raw,
    sale_status_raw,
    primary_as_of_date,
    quality_flags
FROM product_bond_kr
WHERE dataset_version_id IN (SELECT id FROM dataset_version WHERE status = 'ACTIVE')
UNION ALL
SELECT
    product_uid,
    dataset_version_id,
    product_family,
    source_table,
    source_key,
    product_name,
    product_name_normalized,
    manager_or_issuer_raw,
    currency_raw,
    market_raw,
    asset_type_raw,
    investment_region_raw,
    risk_label_raw,
    sale_status_raw,
    primary_as_of_date,
    quality_flags
FROM product_etf_kr
WHERE dataset_version_id IN (SELECT id FROM dataset_version WHERE status = 'ACTIVE')
UNION ALL
SELECT
    product_uid,
    dataset_version_id,
    product_family,
    source_table,
    source_key,
    product_name,
    product_name_normalized,
    manager_or_issuer_raw,
    currency_raw,
    market_raw,
    asset_type_raw,
    investment_region_raw,
    risk_label_raw,
    sale_status_raw,
    primary_as_of_date,
    quality_flags
FROM product_etf_global
WHERE dataset_version_id IN (SELECT id FROM dataset_version WHERE status = 'ACTIVE')
UNION ALL
SELECT
    product_uid,
    dataset_version_id,
    product_family,
    source_table,
    source_key,
    product_name,
    product_name_normalized,
    manager_or_issuer_raw,
    currency_raw,
    market_raw,
    asset_type_raw,
    investment_region_raw,
    risk_label_raw,
    sale_status_raw,
    primary_as_of_date,
    quality_flags
FROM product_fund_public
WHERE dataset_version_id IN (SELECT id FROM dataset_version WHERE status = 'ACTIVE')
"""


def _product_table(name: str, unique_name: str, extra_columns: list[sa.Column]) -> None:
    columns = ENVELOPE_COLUMNS + extra_columns
    op.create_table(
        name,
        *columns,
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_version_id", "product_uid", name=unique_name),
    )
    op.create_index(f"ix_{name}_dataset_version_id", name, ["dataset_version_id"])
    op.create_index(f"ix_{name}_product_uid", name, ["product_uid"])


def upgrade() -> None:
    _product_table(
        "product_bond_kr",
        "uq_product_bond_kr_version_uid",
        [
            sa.Column("pd_no", sa.String(length=64), nullable=True),
            sa.Column("pd_exg_mkt", sa.String(length=32), nullable=True),
            sa.Column("info_base_dt", sa.String(length=16), nullable=True),
            sa.Column("info_seq", sa.Integer(), nullable=True),
            sa.Column("remaining_days", sa.Integer(), nullable=True),
            sa.Column("applied_yield", sa.Numeric(18, 6), nullable=True),
            sa.Column("srfc_irt", sa.Numeric(18, 6), nullable=True),
            sa.Column("dur", sa.Numeric(18, 6), nullable=True),
            sa.Column("eval_price", sa.Numeric(18, 6), nullable=True),
            sa.Column("isu_bal_amt", sa.Numeric(24, 2), nullable=True),
        ],
    )
    _product_table(
        "product_etf_kr",
        "uq_product_etf_kr_version_uid",
        [
            sa.Column("pd_itm_no", sa.String(length=64), nullable=True),
            sa.Column("pd_ticker", sa.String(length=32), nullable=True),
            sa.Column("pd_lste_dt", sa.String(length=16), nullable=True),
            sa.Column("du_er_1d", sa.Numeric(18, 6), nullable=True),
            sa.Column("du_last_aum", sa.Numeric(24, 2), nullable=True),
            sa.Column("cu_charge_rt", sa.Numeric(18, 6), nullable=True),
            sa.Column("cu_base_index", sa.String(length=255), nullable=True),
        ],
    )
    _product_table(
        "product_etf_global",
        "uq_product_etf_global_version_uid",
        [
            sa.Column("pd_itm_no", sa.String(length=64), nullable=True),
            sa.Column("du_clpr", sa.Numeric(18, 6), nullable=True),
            sa.Column("du_last_nav", sa.Numeric(18, 6), nullable=True),
            sa.Column("du_last_aum", sa.Numeric(24, 2), nullable=True),
            sa.Column("du_er_1d", sa.Numeric(18, 6), nullable=True),
            sa.Column("du_val_1d", sa.Numeric(24, 2), nullable=True),
            sa.Column("du_vol_1d", sa.Numeric(24, 2), nullable=True),
            sa.Column("du_clpr_base_dt", sa.Date(), nullable=True),
            sa.Column("du_nav_base_dt", sa.Date(), nullable=True),
            sa.Column("du_base_dt_match_yn", sa.String(length=8), nullable=True),
        ],
    )
    _product_table(
        "product_fund_public",
        "uq_product_fund_public_version_uid",
        [
            sa.Column("itm_no", sa.String(length=64), nullable=True),
            sa.Column("itm_abrv_nm", sa.String(length=255), nullable=True),
            sa.Column("fd_mm1_ern_r", sa.Numeric(18, 6), nullable=True),
            sa.Column("fd_yr1_ern_r", sa.Numeric(18, 6), nullable=True),
            sa.Column("fd_nast_suma", sa.Numeric(24, 2), nullable=True),
            sa.Column("fd_price_bas_dt", sa.Date(), nullable=True),
        ],
    )

    op.create_table(
        "product_metric_value",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("product_uid", sa.String(length=128), nullable=False),
        sa.Column("product_family", sa.String(length=32), nullable=False),
        sa.Column("logical_field_stub", sa.String(length=128), nullable=False),
        sa.Column("source_field", sa.String(length=64), nullable=False),
        sa.Column("raw_value_text", sa.Text(), nullable=True),
        sa.Column("normalized_value_text", sa.Text(), nullable=True),
        sa.Column("normalized_value_numeric", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("quality_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("derivation", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "product_uid",
            "logical_field_stub",
            name="uq_product_metric_value_version_uid_stub",
        ),
    )
    op.create_index(
        "ix_product_metric_value_dataset_version_id",
        "product_metric_value",
        ["dataset_version_id"],
    )
    op.create_index("ix_product_metric_value_product_uid", "product_metric_value", ["product_uid"])

    op.create_table(
        "product_quality_issue",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("product_uid", sa.String(length=128), nullable=False),
        sa.Column("product_family", sa.String(length=32), nullable=False),
        sa.Column("source_field", sa.String(length=64), nullable=False),
        sa.Column("quality_flag", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_version.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_quality_issue_dataset_version_id",
        "product_quality_issue",
        ["dataset_version_id"],
    )

    op.create_table(
        "curation_run",
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
        sa.Column("row_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("flag_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_version_id"),
    )

    op.execute(SEARCH_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS product_search_view")
    op.drop_table("curation_run")
    op.drop_table("product_quality_issue")
    op.drop_table("product_metric_value")
    op.drop_table("product_fund_public")
    op.drop_table("product_etf_global")
    op.drop_table("product_etf_kr")
    op.drop_table("product_bond_kr")
