from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agent.decision import Decision

from app.agent.reason_codes import ReasonCode
from app.query.models import QuerySpec


class EvidenceValidationAction(StrEnum):
    DROP_CANDIDATE = "DROP_CANDIDATE"
    DOWNGRADE_WITH_DISCLOSURE = "DOWNGRADE_WITH_DISCLOSURE"
    BLOCK_ALL = "BLOCK_ALL"
    SYSTEM_INTEGRITY_ERROR = "SYSTEM_INTEGRITY_ERROR"


@dataclass(slots=True)
class EvidenceField:
    logical_field: str
    source_field: str
    value: str
    unit: str | None
    as_of_date: str | None
    derivation: str
    quality_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RelationshipEvidenceItem:
    relation_type: str
    subject_entity_id: str
    object_entity_id: str
    source_document_id: str
    source_title: str
    source_publisher: str
    source_url: str | None
    content_sha256: str
    as_of_date: str | None = None


@dataclass(slots=True)
class DocumentEvidenceItem:
    chunk_id: str
    document_id: str
    chunk_text: str
    source_title: str
    source_publisher: str
    source_url: str | None
    content_sha256: str


@dataclass(slots=True)
class EvidenceBundle:
    product_uid: str
    product_name: str | None
    source_table: str
    source_key: str
    used_fields: list[EvidenceField] = field(default_factory=list)
    relationship_evidence: list[RelationshipEvidenceItem] = field(default_factory=list)
    document_evidence: list[DocumentEvidenceItem] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    selection_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CandidateValidationOutcome:
    product_uid: str
    action: EvidenceValidationAction
    reason: str


@dataclass(slots=True)
class EvidenceValidationResult:
    outcomes: list[CandidateValidationOutcome] = field(default_factory=list)
    bundles: list[EvidenceBundle] = field(default_factory=list)
    evidence_hash: str = ""
    passed: bool = True
    reason_codes: list[ReasonCode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def blocked_product_uids(self) -> list[str]:
        return [
            item.product_uid
            for item in self.outcomes
            if item.action == EvidenceValidationAction.DROP_CANDIDATE
        ]


@dataclass(slots=True)
class AnswerContext:
    question: str
    spec_summary: dict[str, Any]
    decision: Decision
    evidence_bundles: list[EvidenceBundle]
    retrieved_context: str
    relation_evidence: list[RelationshipEvidenceItem] = field(default_factory=list)
    forbidden_phrases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionTrace:
    intent: str
    product_families: list[str]
    selected_retrievers: list[str]
    candidate_counts: dict[str, int]
    decision_state: str
    reason_codes: list[str]
    dataset_version: str
    external_manifest_hash: str | None
    elapsed_ms: int
    query_hash: str


@dataclass(slots=True)
class GuardResult:
    passed: bool
    offending_spans: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def compute_evidence_hash(bundles: list[EvidenceBundle]) -> str:
    payload = []
    for bundle in sorted(bundles, key=lambda item: item.product_uid):
        payload.append(
            {
                "product_uid": bundle.product_uid,
                "source_table": bundle.source_table,
                "source_key": bundle.source_key,
                "used_fields": [
                    {
                        "logical_field": field.logical_field,
                        "source_field": field.source_field,
                        "value": field.value,
                        "unit": field.unit,
                        "as_of_date": field.as_of_date,
                    }
                    for field in bundle.used_fields
                ],
            }
        )
    encoded = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def summarize_spec(spec: QuerySpec) -> dict[str, Any]:
    return {
        "intent": spec.intent.value,
        "product_families": [family.value for family in spec.product_families],
        "filter_count": len(spec.filters),
        "metric_count": len(spec.metrics),
        "limit": spec.limit,
    }
