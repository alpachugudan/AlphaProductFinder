from __future__ import annotations

import pytest
from app.agent.decision import Decision, DecisionState
from app.evidence.models import AnswerContext, EvidenceBundle, EvidenceField
from app.llm.mock_provider import MockLlmProvider


def _context(state: DecisionState, *, missing: list[str] | None = None) -> AnswerContext:
    decision = Decision(
        state=state,
        missing_requirements=missing or [],
        reason_codes=[],
        selected_candidate_ids=["ETF_KR:001"],
    )
    bundles = [
        EvidenceBundle(
            product_uid="ETF_KR:001",
            product_name="Mock ETF",
            source_table="PREF01N001",
            source_key="1",
            used_fields=[
                EvidenceField(
                    logical_field="expense_ratio",
                    source_field="cu_charge_rt",
                    value="0.20",
                    unit="%",
                    as_of_date="2026-08-22",
                    derivation="SOURCE",
                )
            ],
        )
    ]
    return AnswerContext(
        question="test",
        spec_summary={"intent": "FILTER"},
        decision=decision,
        evidence_bundles=bundles,
        retrieved_context="ctx",
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_mock_generate_answer_for_answer_state() -> None:
    provider = MockLlmProvider()
    text = await provider.generate_answer(_context(DecisionState.ANSWER))
    assert text.startswith("ANSWER:")
    assert "ETF_KR:001" in text


@pytest.mark.asyncio(loop_scope="module")
async def test_mock_generate_answer_for_ask_state() -> None:
    provider = MockLlmProvider()
    text = await provider.generate_answer(
        _context(DecisionState.ASK, missing=["투자 지역"])
    )
    assert text.startswith("ASK:")
    assert "투자 지역" in text


@pytest.mark.asyncio(loop_scope="module")
async def test_mock_generate_answer_for_abstain_state() -> None:
    provider = MockLlmProvider()
    text = await provider.generate_answer(_context(DecisionState.ABSTAIN))
    assert text.startswith("ABSTAIN:")
