from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CurationRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ProductEnvelopeMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dataset_version.id"), nullable=False
    )
    source_table: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_family: Mapped[str] = mapped_column(String(32), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    product_name_normalized: Mapped[str | None] = mapped_column(String(512), nullable=True)
    manager_or_issuer_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency_raw: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    asset_type_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    investment_region_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_label_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sale_status_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    primary_as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProductBondKr(Base, ProductEnvelopeMixin):
    __tablename__ = "product_bond_kr"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id", "product_uid", name="uq_product_bond_kr_version_uid"
        ),
    )

    pd_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pd_exg_mkt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    info_base_dt: Mapped[str | None] = mapped_column(String(16), nullable=True)
    info_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_yield: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    srfc_irt: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    dur: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    eval_price: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    isu_bal_amt: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)


class ProductEtfKr(Base, ProductEnvelopeMixin):
    __tablename__ = "product_etf_kr"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "product_uid", name="uq_product_etf_kr_version_uid"),
    )

    pd_itm_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pd_ticker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pd_lste_dt: Mapped[str | None] = mapped_column(String(16), nullable=True)
    du_er_1d: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    du_last_aum: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    cu_charge_rt: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cu_base_index: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ProductEtfGlobal(Base, ProductEnvelopeMixin):
    __tablename__ = "product_etf_global"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id", "product_uid", name="uq_product_etf_global_version_uid"
        ),
    )

    pd_itm_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    du_clpr: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    du_last_nav: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    du_last_aum: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    du_er_1d: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    du_val_1d: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    du_vol_1d: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    du_clpr_base_dt: Mapped[date | None] = mapped_column(Date, nullable=True)
    du_nav_base_dt: Mapped[date | None] = mapped_column(Date, nullable=True)
    du_base_dt_match_yn: Mapped[str | None] = mapped_column(String(8), nullable=True)


class ProductFundPublic(Base, ProductEnvelopeMixin):
    __tablename__ = "product_fund_public"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id", "product_uid", name="uq_product_fund_public_version_uid"
        ),
    )

    itm_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    itm_abrv_nm: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fd_mm1_ern_r: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    fd_yr1_ern_r: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    fd_nast_suma: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    fd_price_bas_dt: Mapped[date | None] = mapped_column(Date, nullable=True)


class ProductMetricValue(Base):
    __tablename__ = "product_metric_value"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "product_uid",
            "logical_field_stub",
            name="uq_product_metric_value_version_uid_stub",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dataset_version.id"), nullable=False
    )
    product_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    product_family: Mapped[str] = mapped_column(String(32), nullable=False)
    logical_field_stub: Mapped[str] = mapped_column(String(128), nullable=False)
    source_field: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    derivation: Mapped[str] = mapped_column(String(64), nullable=False, default="SOURCE")


class ProductQualityIssue(Base):
    __tablename__ = "product_quality_issue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dataset_version.id"), nullable=False
    )
    product_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    product_family: Mapped[str] = mapped_column(String(32), nullable=False)
    source_field: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_flag: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class CurationRun(Base):
    __tablename__ = "curation_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dataset_version.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    flag_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


CURATED_PRODUCT_MODELS: dict[str, type[ProductEnvelopeMixin]] = {
    "product_bond_kr": ProductBondKr,
    "product_etf_kr": ProductEtfKr,
    "product_etf_global": ProductEtfGlobal,
    "product_fund_public": ProductFundPublic,
}

EXPECTED_CURATED_COUNTS: dict[str, int] = {
    "product_bond_kr": 21882,
    "product_etf_kr": 1780,
    "product_etf_global": 6037,
    "product_fund_public": 14716,
}
