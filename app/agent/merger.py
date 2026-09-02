from __future__ import annotations

from app.agent.execution_plan import MergeMode
from app.query.models import QuerySpec
from app.retrieval.models import Candidate, RetrievalResult


def merge_retrieval_results(
    *,
    spec: QuerySpec,
    merge_mode: MergeMode,
    sql_result: RetrievalResult | None,
    relation_result: RetrievalResult | None,
    document_result: RetrievalResult | None,
) -> RetrievalResult:
    """고정 순서로 SQL → Relation → Document 결과 병합"""
    base = sql_result or _empty_result(spec)
    candidates = list(base.candidates)
    relation_evidences = list(base.relation_evidences)
    document_evidences = list(base.document_evidences)
    warnings = list(base.warnings)
    exclusions = list(base.exclusions)
    batches = list(base.batches)
    elapsed_ms = base.elapsed_ms

    if relation_result is not None:
        relation_evidences.extend(relation_result.relation_evidences)
        warnings.extend(relation_result.warnings)
        exclusions.extend(relation_result.exclusions)
        elapsed_ms += relation_result.elapsed_ms
        relation_product_uids = {
            evidence.product_uid
            for evidence in relation_result.relation_evidences
            if evidence.product_uid
        }
        relation_candidate_map = {
            candidate.product_uid: candidate for candidate in relation_result.candidates
        }
        if merge_mode == MergeMode.RELATION_INTERSECT and relation_product_uids:
            # RelationRetriever가 Curated 원천 행으로 보강한 후보를 우선한다. SQL의 top-N을
            # 먼저 자르면 실제 관계 후보가 사라져 근거 검증까지 도달하지 못하는 문제가 있다.
            relation_candidates = [
                relation_candidate_map[uid]
                for uid in relation_product_uids
                if uid in relation_candidate_map
            ]
            if relation_candidates:
                sql_candidate_map = {candidate.product_uid: candidate for candidate in candidates}
                for candidate in relation_candidates:
                    sql_candidate = sql_candidate_map.get(candidate.product_uid)
                    if sql_candidate is not None:
                        candidate.selection_reasons = _merge_strings(
                            sql_candidate.selection_reasons,
                            candidate.selection_reasons,
                        )
                candidates = relation_candidates
            else:
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.product_uid in relation_product_uids
                ]
        elif not candidates and relation_result.candidates:
            candidates = list(relation_result.candidates)

    if document_result is not None:
        document_evidences.extend(document_result.document_evidences)
        warnings.extend(document_result.warnings)
        elapsed_ms += document_result.elapsed_ms

    candidates = _dedupe_candidates(candidates)
    return RetrievalResult(
        spec=spec,
        product_families=list(spec.product_families),
        batches=batches,
        candidates=candidates,
        count_before_filter=base.count_before_filter,
        count_after_filter=base.count_after_filter,
        count_after_quality=base.count_after_quality,
        count_final=len(candidates),
        applied_filters=base.applied_filters,
        applied_sorts=base.applied_sorts,
        exclusions=exclusions,
        warnings=warnings,
        elapsed_ms=elapsed_ms,
        aggregate_value=base.aggregate_value,
        aggregate_op=base.aggregate_op,
        relation_evidences=relation_evidences,
        document_evidences=document_evidences,
    )


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    order: list[str] = []
    for candidate in candidates:
        if candidate.product_uid not in merged:
            merged[candidate.product_uid] = candidate
            order.append(candidate.product_uid)
            continue
        existing = merged[candidate.product_uid]
        existing.selection_reasons = _merge_strings(
            existing.selection_reasons,
            candidate.selection_reasons,
        )
        existing.quality_flags = _merge_strings(existing.quality_flags, candidate.quality_flags)
        if candidate.metrics_used:
            existing.metrics_used = candidate.metrics_used
    return [merged[uid] for uid in order]


def _merge_strings(left: list[str], right: list[str]) -> list[str]:
    seen = set(left)
    merged = list(left)
    for item in right:
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _empty_result(spec: QuerySpec) -> RetrievalResult:
    return RetrievalResult(
        spec=spec,
        product_families=list(spec.product_families),
        batches=[],
        candidates=[],
        count_before_filter=0,
        count_after_filter=0,
        count_after_quality=0,
        count_final=0,
        applied_filters=[],
        applied_sorts=[],
        exclusions=[],
        warnings=[],
        elapsed_ms=0,
    )
