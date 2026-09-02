from __future__ import annotations

import uuid

from app.agent.decision import Decision, DecisionState
from app.agent.execution_plan import (
    DEFAULT_TIMEOUT_BUDGET,
    ExecutionPlan,
    MergeMode,
    RetrieverKind,
    RetrieverSubPlan,
    compute_spec_hash,
)
from app.agent.reason_codes import VALIDATION_TO_REASON, ReasonCode
from app.config.settings import Settings, get_settings
from app.curated.quality import QualityFlag, QualitySeverity, severity_for_flag
from app.query.enums import Intent
from app.query.models import QuerySpec
from app.query.ontology_grounding import AmbiguousGrounding, GroundingResult
from app.query.registry import FieldRegistry, get_field_registry
from app.query.validator import ValidationIssue, validate_queryspec
from app.retrieval.models import Candidate, RetrievalResult


def select_retrievers(spec: QuerySpec) -> list[RetrieverSubPlan]:
    """intent·relationship_filters 기준 allowlist Retriever 선택"""
    if spec.intent == Intent.UNSUPPORTED_PREDICTION:
        return []

    selected: dict[RetrieverKind, bool] = {}

    if spec.intent == Intent.EXPLAIN_TERM:
        selected[RetrieverKind.DOCUMENT] = True
        if spec.relationship_filters:
            selected[RetrieverKind.RELATION] = False
    elif spec.intent == Intent.RELATION_SEARCH:
        selected[RetrieverKind.SQL] = True
        selected[RetrieverKind.RELATION] = True
    elif spec.intent == Intent.AGGREGATE:
        selected[RetrieverKind.SQL] = True
        if spec.relationship_filters:
            selected[RetrieverKind.RELATION] = True
    else:
        selected[RetrieverKind.SQL] = True
        if spec.relationship_filters:
            selected[RetrieverKind.RELATION] = True

    plans: list[RetrieverSubPlan] = []
    for kind, required in selected.items():
        plans.append(
            RetrieverSubPlan(
                kind=kind,
                required=required,
                timeout_seconds=DEFAULT_TIMEOUT_BUDGET[kind],
            )
        )
    return plans


def resolve_merge_mode(spec: QuerySpec) -> MergeMode:
    if spec.intent == Intent.EXPLAIN_TERM and not spec.filters:
        return MergeMode.DOCUMENT_ONLY
    if spec.relationship_filters:
        return MergeMode.RELATION_INTERSECT
    return MergeMode.SQL_PRIMARY


def build_execution_plan(
    spec: QuerySpec,
    *,
    dataset_version_label: str,
    query_id: str | None = None,
    settings: Settings | None = None,
) -> ExecutionPlan:
    active_settings = settings or get_settings()
    retrievers = select_retrievers(spec)
    retriever_total = sum(item.timeout_seconds for item in retrievers)
    timeout_budget = min(
        active_settings.internal_timeout_seconds,
        retriever_total or active_settings.internal_timeout_seconds,
    )
    return ExecutionPlan(
        query_id=query_id or str(uuid.uuid4()),
        dataset_version_label=dataset_version_label,
        spec_hash=compute_spec_hash(spec),
        spec=spec,
        retrievers=retrievers,
        merge_mode=resolve_merge_mode(spec),
        timeout_budget_seconds=timeout_budget,
        required_evidence_fields=[
            "product_uid",
            "source_table",
            "source_key",
            "metrics_used.as_of_date",
        ],
        comparison_compatibility_rules=["family_separated_compare"],
        expected_coverage_requirements=(
            ["official_source_document"] if spec.relationship_filters else []
        ),
    )


def decision_from_validation(
    spec: QuerySpec,
    issues: list[ValidationIssue],
    grounding_results: list[GroundingResult] | None = None,
) -> Decision | None:
    if spec.intent == Intent.UNSUPPORTED_PREDICTION:
        return Decision(
            state=DecisionState.ABSTAIN,
            reason_codes=[ReasonCode.UNSUPPORTED_PREDICTION],
            execution_summary={"stage": "VALIDATE"},
        )

    if issues:
        askable = [issue for issue in issues if issue.askable]
        blocking = [issue for issue in issues if not issue.askable]
        if blocking:
            codes = [
                VALIDATION_TO_REASON.get(issue.code, ReasonCode.VALIDATION_FAILED)
                for issue in blocking
            ]
            return Decision(
                state=DecisionState.ABSTAIN,
                reason_codes=_dedupe_codes(codes),
                missing_requirements=[issue.message for issue in blocking[:2]],
                execution_summary={"stage": "VALIDATE", "issue_count": len(blocking)},
            )
        if askable:
            codes = [
                VALIDATION_TO_REASON.get(issue.code, ReasonCode.MISSING_FILTERS)
                for issue in askable
            ]
            return Decision(
                state=DecisionState.ASK,
                reason_codes=_dedupe_codes(codes),
                missing_requirements=[issue.message for issue in askable[:2]],
                user_message_requirements=[issue.json_path for issue in askable[:2]],
                execution_summary={"stage": "VALIDATE", "issue_count": len(askable)},
            )

    if grounding_results:
        ambiguous = [item for item in grounding_results if isinstance(item, AmbiguousGrounding)]
        if ambiguous:
            return Decision(
                state=DecisionState.ASK,
                reason_codes=[ReasonCode.AMBIGUOUS_ENTITY],
                missing_requirements=[
                    f"ambiguous token: {item.token}" for item in ambiguous[:2]
                ],
                execution_summary={"stage": "GROUND"},
            )
    return None


def decide_preliminary(
    spec: QuerySpec,
    plan: ExecutionPlan,
    merged: RetrievalResult | None,
) -> Decision:
    if merged is None:
        return Decision(
            state=DecisionState.ABSTAIN,
            reason_codes=[ReasonCode.NO_VALID_CANDIDATE],
            execution_summary={"stage": "RETRIEVE", "candidate_count": 0},
        )

    if spec.intent == Intent.RELATION_SEARCH and not merged.relation_evidences:
        unresolved = any(item.startswith("UNRESOLVED_ENTITY:") for item in merged.warnings)
        code = ReasonCode.ENTITY_NOT_FOUND if unresolved else ReasonCode.EXTERNAL_EVIDENCE_MISSING
        return Decision(
            state=DecisionState.ABSTAIN,
            reason_codes=[code],
            warnings=list(merged.warnings),
            execution_summary={"stage": "RETRIEVE", "relation_count": 0},
        )

    if spec.intent == Intent.EXPLAIN_TERM:
        if merged.document_evidences:
            return Decision(
                state=DecisionState.PRE_ANSWER,
                reason_codes=[ReasonCode.EVIDENCE_READY],
                selected_candidate_ids=[],
                execution_summary={
                    "stage": "PRE_ANSWER",
                    "document_count": len(merged.document_evidences),
                },
            )
        return Decision(
            state=DecisionState.ABSTAIN,
            reason_codes=[ReasonCode.EXTERNAL_EVIDENCE_MISSING],
            warnings=list(merged.warnings),
        )

    eligible, blocked = _split_candidates_by_quality(merged.candidates)
    if (
        spec.intent == Intent.RELATION_SEARCH
        and not eligible
        and merged.relation_evidences
        and all(item.product_uid is None for item in merged.relation_evidences)
    ):
        # 기업 간 관계는 상품 Curated 행이 없더라도 동결된 공식 문서로 직접 검증할 수 있다.
        return Decision(
            state=DecisionState.PRE_ANSWER,
            reason_codes=[ReasonCode.EVIDENCE_READY],
            execution_summary={
                "stage": "PRE_ANSWER",
                "relation_count": len(merged.relation_evidences),
                "relation_only": True,
            },
        )

    if not eligible and merged.candidates:
        return Decision(
            state=DecisionState.ABSTAIN,
            reason_codes=[ReasonCode.QUALITY_BLOCKED],
            warnings=[f"blocked_candidates={len(blocked)}"],
            execution_summary={"stage": "PRE_ANSWER", "blocked_count": len(blocked)},
        )

    if not eligible and spec.intent != Intent.AGGREGATE:
        return Decision(
            state=DecisionState.ABSTAIN,
            reason_codes=[ReasonCode.NO_VALID_CANDIDATE],
            warnings=list(merged.warnings),
            execution_summary={"stage": "RETRIEVE", "candidate_count": 0},
        )

    if spec.intent == Intent.AGGREGATE and merged.aggregate_value is not None:
        return Decision(
            state=DecisionState.PRE_ANSWER,
            reason_codes=[ReasonCode.EVIDENCE_READY],
            selected_candidate_ids=[],
            execution_summary={"stage": "PRE_ANSWER", "aggregate": str(merged.aggregate_value)},
        )

    return Decision(
        state=DecisionState.PRE_ANSWER,
        reason_codes=[ReasonCode.EVIDENCE_READY],
        selected_candidate_ids=[item.product_uid for item in eligible],
        warnings=list(merged.warnings),
        execution_summary={
            "stage": "PRE_ANSWER",
            "candidate_count": len(eligible),
            "blocked_count": len(blocked),
        },
    )


def validate_and_plan(
    spec: QuerySpec,
    *,
    dataset_version_label: str,
    registry: FieldRegistry | None = None,
    grounding_results: list[GroundingResult] | None = None,
) -> tuple[Decision | None, ExecutionPlan | None]:
    active_registry = registry or get_field_registry()
    issues = validate_queryspec(spec, active_registry)
    early = decision_from_validation(spec, issues, grounding_results)
    if early is not None:
        return early, None
    plan = build_execution_plan(spec, dataset_version_label=dataset_version_label)
    return None, plan


def _split_candidates_by_quality(
    candidates: list[Candidate],
) -> tuple[list[Candidate], list[Candidate]]:
    eligible: list[Candidate] = []
    blocked: list[Candidate] = []
    for candidate in candidates:
        if _is_blocked_candidate(candidate):
            blocked.append(candidate)
        else:
            eligible.append(candidate)
    return eligible, blocked


def _is_blocked_candidate(candidate: Candidate) -> bool:
    for flag_name in candidate.quality_flags:
        try:
            severity = severity_for_flag(QualityFlag(flag_name))
        except ValueError:
            continue
        if severity == QualitySeverity.BLOCK_ANSWER:
            return True
    for metric in candidate.metrics_used:
        if (
            metric.raw_value == 0
            and "INVALID_FOR_DECISION" in metric.quality_flags
        ):
            return True
        for flag_name in metric.quality_flags:
            try:
                severity = severity_for_flag(QualityFlag(flag_name))
            except ValueError:
                continue
            if severity == QualitySeverity.BLOCK_ANSWER:
                return True
    return False


def _dedupe_codes(codes: list[ReasonCode]) -> list[ReasonCode]:
    seen: set[ReasonCode] = set()
    ordered: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered
