from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.evidence.models import (
    DocumentEvidenceItem,
    EvidenceBundle,
    EvidenceField,
    RelationshipEvidenceItem,
)
from app.query.enums import ProductFamily
from app.query.registry import FieldRegistry, get_field_registry
from app.retrieval.models import (
    DocumentEvidence,
    MetricReference,
    RelationEvidence,
    RetrievalResult,
)


def build_evidence_bundles(
    merged: RetrievalResult,
    *,
    selected_product_uids: list[str],
    registry: FieldRegistry | None = None,
) -> list[EvidenceBundle]:
    active_registry = registry or get_field_registry()
    candidate_map = {item.product_uid: item for item in merged.candidates}
    bundles: list[EvidenceBundle] = []
    relation_by_product = _index_relations(merged.relation_evidences)
    documents = [
        _to_document_item(item)
        for item in merged.document_evidences
    ]

    for product_uid in selected_product_uids:
        candidate = candidate_map.get(product_uid)
        if candidate is None:
            continue
        used_fields = [
            _to_evidence_field(metric, candidate.product_family, active_registry)
            for metric in candidate.metrics_used
        ]
        bundles.append(
            EvidenceBundle(
                product_uid=candidate.product_uid,
                product_name=candidate.product_name,
                source_table=candidate.source_table,
                source_key=candidate.source_key,
                used_fields=used_fields,
                relationship_evidence=relation_by_product.get(product_uid, []),
                document_evidence=documents,
                quality_flags=list(candidate.quality_flags),
                selection_reasons=list(candidate.selection_reasons),
            )
        )
    return bundles


def _index_relations(
    relations: list[RelationEvidence],
) -> dict[str, list[RelationshipEvidenceItem]]:
    indexed: dict[str, list[RelationshipEvidenceItem]] = {}
    for item in relations:
        product_uid = item.product_uid or item.subject_entity_id
        indexed.setdefault(product_uid, []).append(_to_relationship_item(item))
    return indexed


def build_relationship_evidence_items(
    relations: list[RelationEvidence],
) -> list[RelationshipEvidenceItem]:
    """상품 행에 귀속되지 않는 기업 관계 답변의 공식 출처를 보존한다."""
    return [_to_relationship_item(item) for item in relations]


def _to_evidence_field(
    metric: MetricReference,
    _family: ProductFamily,
    registry: FieldRegistry,
) -> EvidenceField:
    definition = registry.get(metric.logical_field)
    unit = definition.unit if definition else None
    return EvidenceField(
        logical_field=metric.logical_field,
        source_field=metric.source_field,
        value=_stringify(metric.raw_value) or "",
        unit=unit,
        as_of_date=_stringify(metric.as_of_date),
        derivation="SOURCE",
        quality_flags=list(metric.quality_flags),
    )


def _to_relationship_item(item: RelationEvidence) -> RelationshipEvidenceItem:
    return RelationshipEvidenceItem(
        relation_type=item.relation_type,
        subject_entity_id=item.subject_entity_id,
        object_entity_id=item.object_entity_id,
        source_document_id=item.source_document_id,
        source_title=item.source_title,
        source_publisher=item.source_publisher,
        source_url=item.source_url,
        content_sha256=item.content_sha256,
        as_of_date=_stringify(item.as_of_date),
    )


def _to_document_item(item: DocumentEvidence) -> DocumentEvidenceItem:
    return DocumentEvidenceItem(
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        chunk_text=item.chunk_text,
        source_title=item.source_title,
        source_publisher=item.source_publisher,
        source_url=item.source_url,
        content_sha256=item.content_sha256,
    )


def _stringify(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
