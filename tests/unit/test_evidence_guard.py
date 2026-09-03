from __future__ import annotations

from app.agent.decision import Decision, DecisionState
from app.evidence.answer_guard import guard_answer
from app.evidence.answer_service import _safe_answer_fallback
from app.evidence.models import EvidenceBundle


def _decision(state: DecisionState) -> Decision:
    return Decision(state=state, selected_candidate_ids=["ETF_KR:001"])


def _bundle(name: str = "Test ETF") -> EvidenceBundle:
    return EvidenceBundle(
        product_uid="ETF_KR:001",
        product_name=name,
        source_table="PREF01N001",
        source_key="1",
    )


def test_guard_blocks_forbidden_phrase() -> None:
    result = guard_answer(
        "이 상품은 추천합니다",
        decision=_decision(DecisionState.ANSWER),
        evidence_bundles=[_bundle()],
    )
    assert not result.passed
    assert "FORBIDDEN_PHRASE" in result.reason_codes


def test_guard_blocks_hallucinated_product_uid() -> None:
    result = guard_answer(
        "후보 ETF_GLOBAL:UNKNOWN 입니다",
        decision=_decision(DecisionState.ANSWER),
        evidence_bundles=[_bundle()],
    )
    assert not result.passed
    assert "HALLUCINATED_PRODUCT" in result.reason_codes


def test_guard_blocks_candidate_name_in_abstain() -> None:
    result = guard_answer(
        "ABSTAIN: Test ETF 근거 부족",
        decision=_decision(DecisionState.ABSTAIN),
        evidence_bundles=[_bundle()],
    )
    assert not result.passed
    assert "UNEXPECTED_CANDIDATE_IN_NON_ANSWER" in result.reason_codes


def test_guard_passes_clean_answer() -> None:
    result = guard_answer(
        "ANSWER: ETF_KR:001 / metric=0.20%",
        decision=_decision(DecisionState.ANSWER),
        evidence_bundles=[_bundle()],
    )
    assert result.passed


def test_guard_blocks_wrong_decision_prefix() -> None:
    result = guard_answer(
        "ANSWER: 근거가 없어 판단할 수 없습니다.",
        decision=_decision(DecisionState.ABSTAIN),
        evidence_bundles=[],
    )
    assert not result.passed
    assert result.reason_codes == ["STATE_PREFIX_MISMATCH"]


def test_safe_fallback_passes_answer_guard() -> None:
    decision = _decision(DecisionState.ANSWER)
    fallback = _safe_answer_fallback(decision)

    result = guard_answer(fallback, decision=decision, evidence_bundles=[])

    assert result.passed
