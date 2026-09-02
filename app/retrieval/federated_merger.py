from __future__ import annotations

from decimal import Decimal

from app.query.enums import ProductFamily
from app.query.models import QuerySpec
from app.retrieval.models import (
    Candidate,
    CandidateBatch,
    DocumentEvidence,
    RelationEvidence,
    RetrievalResult,
    SafeQueryPlan,
)


def merge_cross_family(
    batches: list[CandidateBatch],
    *,
    families: list[ProductFamily],
    limit: int,
    comparable_metric: str | None = None,
) -> list[Candidate]:
    if comparable_metric:
        combined: list[Candidate] = []
        for batch in batches:
            combined.extend(batch.candidates)
        combined.sort(key=lambda item: item.tie_break_key or item.source_key)
        return combined[:limit]

    merged: list[Candidate] = []
    per_family = {batch.family: list(batch.candidates) for batch in batches}
    order = [family for family in families if family in per_family]
    indices = dict.fromkeys(order, 0)
    while len(merged) < limit:
        added = False
        for family in order:
            items = per_family[family]
            idx = indices[family]
            if idx >= len(items):
                continue
            candidate = items[idx]
            candidate.selection_reasons.append("CROSS_FAMILY_ROUND_ROBIN")
            merged.append(candidate)
            indices[family] = idx + 1
            added = True
            if len(merged) >= limit:
                break
        if not added:
            break
    return merged


def build_retrieval_result(
    *,
    spec: QuerySpec,
    plan: SafeQueryPlan,
    batches: list[CandidateBatch],
    candidates: list[Candidate],
    elapsed_ms: int,
    warnings: list[str] | None = None,
    aggregate_value: Decimal | None = None,
    aggregate_op: str | None = None,
    relation_evidences: list[RelationEvidence] | None = None,
    document_evidences: list[DocumentEvidence] | None = None,
) -> RetrievalResult:
    exclusions = []
    for batch in batches:
        exclusions.extend(batch.exclusions)
    return RetrievalResult(
        spec=spec,
        product_families=list(plan.product_families),
        batches=batches,
        candidates=candidates,
        count_before_filter=sum(batch.count_before_filter for batch in batches),
        count_after_filter=sum(batch.count_after_filter for batch in batches),
        count_after_quality=sum(batch.count_after_quality for batch in batches),
        count_final=len(candidates),
        applied_filters=list(plan.filters),
        applied_sorts=list(plan.sorts),
        exclusions=exclusions,
        warnings=warnings or [],
        elapsed_ms=elapsed_ms,
        aggregate_value=aggregate_value,
        aggregate_op=aggregate_op,
        relation_evidences=relation_evidences or [],
        document_evidences=document_evidences or [],
    )
