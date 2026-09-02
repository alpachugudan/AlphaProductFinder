from __future__ import annotations

import re

from app.agent.decision import Decision, DecisionState
from app.evidence.models import EvidenceBundle, GuardResult, RelationshipEvidenceItem

FORBIDDEN_PHRASES = (
    "추천합니다",
    "가장 좋은 상품입니다",
    "안전합니다",
    "지금 사는 것이 좋습니다",
    "앞으로 오를 것입니다",
    "높은 수익이 기대됩니다",
)

FUTURE_ASSERTION_PATTERN = re.compile(r"(오를|내릴|상승|하락).*(것|예상|전망)")


def guard_answer(
    answer_text: str,
    *,
    decision: Decision,
    evidence_bundles: list[EvidenceBundle],
    relation_evidence: list[RelationshipEvidenceItem] | None = None,
) -> GuardResult:
    offending: list[str] = []
    reason_codes: list[str] = []

    expected_prefix = f"{decision.state.value}:"
    if not answer_text.lstrip().startswith(expected_prefix):
        offending.append(expected_prefix)
        reason_codes.append("STATE_PREFIX_MISMATCH")

    for phrase in FORBIDDEN_PHRASES:
        if phrase in answer_text:
            offending.append(phrase)
            reason_codes.append("FORBIDDEN_PHRASE")

    if FUTURE_ASSERTION_PATTERN.search(answer_text):
        offending.append("future_assertion")
        reason_codes.append("FUTURE_ASSERTION")

    allowed_uids = {bundle.product_uid for bundle in evidence_bundles}
    allowed_uids.update(
        entity_id
        for relation in relation_evidence or []
        for entity_id in (relation.subject_entity_id, relation.object_entity_id)
    )
    for token in re.findall(r"[A-Z0-9_]+:[A-Za-z0-9._-]+", answer_text):
        if token not in allowed_uids:
            offending.append(token)
            reason_codes.append("HALLUCINATED_PRODUCT")

    if decision.state in {DecisionState.ASK, DecisionState.ABSTAIN}:
        for bundle in evidence_bundles:
            if bundle.product_name and bundle.product_name in answer_text:
                offending.append(bundle.product_name)
                reason_codes.append("UNEXPECTED_CANDIDATE_IN_NON_ANSWER")

    passed = not offending
    return GuardResult(passed=passed, offending_spans=offending, reason_codes=_dedupe(reason_codes))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
