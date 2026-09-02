from __future__ import annotations

from app.agent.decision import Decision, DecisionState
from app.agent.orchestrator import finalize_decision
from app.agent.policy_engine import (
    build_execution_plan,
    decide_preliminary,
    decision_from_validation,
)
from app.agent.reason_codes import ReasonCode
from app.curated.quality import QualityFlag
from app.evidence.models import (
    CandidateValidationOutcome,
    EvidenceValidationAction,
    EvidenceValidationResult,
)
from app.query.enums import Intent, ProductFamily
from app.query.models import QuerySpec
from app.query.validator import ValidationIssue
from app.retrieval.models import Candidate, RetrievalResult


def test_validation_askable_issue_returns_ask() -> None:
    spec = QuerySpec(intent=Intent.FILTER, product_families=[ProductFamily.ETF_KR])
    issues = [
        ValidationIssue(
            code="MISSING_FILTERS",
            message="FILTER requires at least one filter",
            json_path="$.filters",
            askable=True,
        )
    ]
    decision = decision_from_validation(spec, issues)
    assert decision is not None
    assert decision.state == DecisionState.ASK
    assert ReasonCode.MISSING_FILTERS in decision.reason_codes


def test_unsupported_prediction_abstains_without_retrieval() -> None:
    spec = QuerySpec(intent=Intent.UNSUPPORTED_PREDICTION, product_families=[ProductFamily.ETF_KR])
    decision = decision_from_validation(spec, [])
    assert decision is not None
    assert decision.state == DecisionState.ABSTAIN
    assert decision.reason_codes == [ReasonCode.UNSUPPORTED_PREDICTION]


def test_no_candidates_abstains_without_relaxation() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "investment_region", "operator": "CONTAINS", "value": "없는지역"}],
    )
    plan = build_execution_plan(spec, dataset_version_label="2026-07-11-baseline")
    merged = RetrievalResult(
        spec=spec,
        product_families=[ProductFamily.ETF_KR],
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
        elapsed_ms=1,
    )
    decision = decide_preliminary(spec, plan, merged)
    assert decision.state == DecisionState.ABSTAIN
    assert ReasonCode.NO_VALID_CANDIDATE in decision.reason_codes


def test_quality_blocked_candidate_abstains_when_all_blocked() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "investment_region", "operator": "CONTAINS", "value": "미국"}],
    )
    plan = build_execution_plan(spec, dataset_version_label="2026-07-11-baseline")
    blocked = Candidate(
        product_uid="ETF_KR:001",
        product_family=ProductFamily.ETF_KR,
        source_table="PREF01N001",
        source_key="1",
        product_name="blocked",
        quality_flags=[QualityFlag.JOIN_CONTAMINATION.value],
    )
    merged = RetrievalResult(
        spec=spec,
        product_families=[ProductFamily.ETF_KR],
        batches=[],
        candidates=[blocked],
        count_before_filter=1,
        count_after_filter=1,
        count_after_quality=0,
        count_final=1,
        applied_filters=[],
        applied_sorts=[],
        exclusions=[],
        warnings=[],
        elapsed_ms=1,
    )
    decision = decide_preliminary(spec, plan, merged)
    assert decision.state == DecisionState.ABSTAIN
    assert ReasonCode.QUALITY_BLOCKED in decision.reason_codes


def test_partial_quality_block_can_finalize_to_answer() -> None:
    preliminary = Decision(
        state=DecisionState.PRE_ANSWER,
        selected_candidate_ids=["ETF_KR:A", "ETF_KR:B"],
    )
    final = finalize_decision(
        preliminary,
        EvidenceValidationResult(
            outcomes=[
                CandidateValidationOutcome(
                    product_uid="ETF_KR:B",
                    action=EvidenceValidationAction.DROP_CANDIDATE,
                    reason="integrity",
                )
            ]
        ),
    )
    assert final.state == DecisionState.ANSWER
    assert final.selected_candidate_ids == ["ETF_KR:A"]
    assert ReasonCode.PARTIAL_CANDIDATE_REMOVED in final.reason_codes


def test_finalize_all_blocked_abstains() -> None:
    preliminary = Decision(
        state=DecisionState.PRE_ANSWER,
        selected_candidate_ids=["ETF_KR:A"],
    )
    final = finalize_decision(
        preliminary,
        EvidenceValidationResult(
            outcomes=[
                CandidateValidationOutcome(
                    product_uid="ETF_KR:A",
                    action=EvidenceValidationAction.DROP_CANDIDATE,
                    reason="integrity",
                )
            ],
            reason_codes=[ReasonCode.QUALITY_BLOCKED],
            passed=False,
        ),
    )
    assert final.state == DecisionState.ABSTAIN
    assert ReasonCode.QUALITY_BLOCKED in final.reason_codes


def test_execution_plan_timeout_within_internal_budget() -> None:
    spec = QuerySpec(
        intent=Intent.RELATION_SEARCH,
        product_families=[ProductFamily.ETF_KR],
        relationship_filters=[
            {"relation": "HOLDS", "target_entity": "삼성전자"},
        ],
    )
    plan = build_execution_plan(spec, dataset_version_label="2026-07-11-baseline")
    assert plan.timeout_budget_seconds <= 120
    assert plan.timeout_budget_seconds > 0
