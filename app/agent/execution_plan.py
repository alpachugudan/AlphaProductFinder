from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum

from app.query.models import QuerySpec


class RetrieverKind(StrEnum):
    SQL = "SQL"
    RELATION = "RELATION"
    DOCUMENT = "DOCUMENT"


class MergeMode(StrEnum):
    SQL_PRIMARY = "SQL_PRIMARY"
    RELATION_INTERSECT = "RELATION_INTERSECT"
    DOCUMENT_ONLY = "DOCUMENT_ONLY"


@dataclass(slots=True)
class RetrieverSubPlan:
    kind: RetrieverKind
    required: bool
    timeout_seconds: int


@dataclass(slots=True)
class ExecutionPlan:
    query_id: str
    dataset_version_label: str
    spec_hash: str
    spec: QuerySpec
    retrievers: list[RetrieverSubPlan]
    merge_mode: MergeMode
    timeout_budget_seconds: int
    required_evidence_fields: list[str] = field(default_factory=list)
    comparison_compatibility_rules: list[str] = field(default_factory=list)
    expected_coverage_requirements: list[str] = field(default_factory=list)


def compute_spec_hash(spec: QuerySpec) -> str:
    payload = spec.model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


DEFAULT_TIMEOUT_BUDGET = {
    RetrieverKind.SQL: 60,
    RetrieverKind.RELATION: 30,
    RetrieverKind.DOCUMENT: 20,
}
