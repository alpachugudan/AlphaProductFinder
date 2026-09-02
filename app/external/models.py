from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExternalIngestionStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ExternalIngestionRun(Base):
    __tablename__ = "external_ingestion_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceDocument(Base):
    __tablename__ = "source_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    local_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    usage_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)


class Entity(Base):
    __tablename__ = "entity"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    identifiers_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class EntityAlias(Base):
    __tablename__ = "entity_alias"
    __table_args__ = (
        UniqueConstraint("normalized_alias", "entity_id", name="uq_entity_alias_norm_entity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("entity.entity_id"), nullable=False
    )
    alias_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_document_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("source_document.document_id"), nullable=False
    )
    match_method: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="APPROVED")


class ProductHolding(Base):
    __tablename__ = "product_holding"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    holding_entity_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("entity.entity_id"), nullable=False
    )
    holding_name_raw: Mapped[str] = mapped_column(String(512), nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_document_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("source_document.document_id"), nullable=False
    )
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    coverage_status: Mapped[str] = mapped_column(String(64), nullable=False, default="ACTIVE")


class EntityRelation(Base):
    __tablename__ = "entity_relation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subject_entity_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("entity.entity_id"), nullable=False
    )
    object_entity_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("entity.entity_id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_document_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("source_document.document_id"), nullable=False
    )
    confidence_basis: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="APPROVED")
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class DocumentChunk(Base):
    __tablename__ = "document_chunk"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    document_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("source_document.document_id"), nullable=False
    )
    entity_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(32), nullable=False)
