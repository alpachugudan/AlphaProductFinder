from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.query.enums import Direction, Operator, ProductFamily
from app.query.models import QuerySpec


@dataclass(slots=True)
class RetrievalContext:
    dataset_version_id: int
    dataset_version_label: str
    session: Session
    external_version: str = "none"


@dataclass(slots=True)
class MetricReference:
    logical_field: str
    source_field: str
    raw_value: Any
    as_of_date: Any = None
    quality_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Candidate:
    product_uid: str
    product_family: ProductFamily
    source_table: str
    source_key: str
    product_name: str | None
    metrics_used: list[MetricReference] = field(default_factory=list)
    selection_reasons: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    stable_rank: int | None = None
    tie_break_key: str | None = None


@dataclass(slots=True)
class ExclusionCount:
    reason_code: str
    count: int


@dataclass(slots=True)
class SafeFilter:
    logical_field: str
    operator: Operator
    value: Any | None


@dataclass(slots=True)
class SafeSort:
    logical_field: str
    direction: Direction
    priority: int | None = None


@dataclass(slots=True)
class SafeQueryPlan:
    product_families: list[ProductFamily]
    filters: list[SafeFilter]
    sorts: list[SafeSort]
    limit: int
    metrics: list[str]


@dataclass(slots=True)
class CandidateBatch:
    family: ProductFamily
    candidates: list[Candidate]
    count_before_filter: int
    count_after_filter: int
    count_after_quality: int
    exclusions: list[ExclusionCount] = field(default_factory=list)


@dataclass(slots=True)
class RetrievalResult:
    spec: QuerySpec
    product_families: list[ProductFamily]
    batches: list[CandidateBatch]
    candidates: list[Candidate]
    count_before_filter: int
    count_after_filter: int
    count_after_quality: int
    count_final: int
    applied_filters: list[SafeFilter]
    applied_sorts: list[SafeSort]
    exclusions: list[ExclusionCount]
    warnings: list[str]
    elapsed_ms: int
    aggregate_value: Decimal | None = None
    aggregate_op: str | None = None
    relation_evidences: list[RelationEvidence] = field(default_factory=list)
    document_evidences: list[DocumentEvidence] = field(default_factory=list)


@dataclass(slots=True)
class RelationEvidence:
    relation_type: str
    subject_entity_id: str
    object_entity_id: str
    source_document_id: str
    source_title: str
    source_publisher: str
    source_url: str | None
    content_sha256: str
    as_of_date: Any = None
    quality_flags: list[str] = field(default_factory=list)
    coverage_status: str = "ACTIVE"
    product_uid: str | None = None
    holding_name_raw: str | None = None
    weight: float | None = None
    weight_unit: str | None = None
    match_method: str | None = None
    confidence_basis: str | None = None


@dataclass(slots=True)
class DocumentEvidence:
    chunk_id: str
    document_id: str
    chunk_text: str
    source_title: str
    source_publisher: str
    source_url: str | None
    content_sha256: str
    score: float
    embedding_version: str
