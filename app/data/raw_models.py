from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DatasetVersionStatus(StrEnum):
    LOADING = "LOADING"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"


class IngestionRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class DatasetVersion(Base):
    __tablename__ = "dataset_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ingestion_runs: Mapped[list[IngestionRun]] = relationship(back_populates="dataset_version")


class IngestionRun(Base):
    __tablename__ = "ingestion_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dataset_version.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="ingestion_runs")


class RawRowMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dataset_version.id"), nullable=False
    )
    source_table: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    value_states: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RawBondKr(Base, RawRowMixin):
    __tablename__ = "raw_bond_kr"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "source_key", name="uq_raw_bond_kr_version_key"),
    )


class RawEtfKr(Base, RawRowMixin):
    __tablename__ = "raw_etf_kr"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "source_key", name="uq_raw_etf_kr_version_key"),
    )


class RawEtfGlobal(Base, RawRowMixin):
    __tablename__ = "raw_etf_global"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id", "source_key", name="uq_raw_etf_global_version_key"
        ),
    )


class RawFund(Base, RawRowMixin):
    __tablename__ = "raw_fund"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "source_key", name="uq_raw_fund_version_key"),
    )


RAW_TABLE_MODELS: dict[str, type[RawRowMixin]] = {
    "raw_bond_kr": RawBondKr,
    "raw_etf_kr": RawEtfKr,
    "raw_etf_global": RawEtfGlobal,
    "raw_fund": RawFund,
}
