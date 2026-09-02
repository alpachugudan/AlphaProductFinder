from __future__ import annotations

import json

from app.agent.decision import Decision, DecisionState
from app.agent.orchestrator import AgentRunResult
from app.agent.reason_codes import ReasonCode
from app.evidence.models import ExecutionTrace
from app.evidence.think_trace import (
    ALLOWED_TRACE_KEYS,
    build_execution_trace,
    serialize_think_trace,
)
from app.query.enums import Intent, ProductFamily
from app.query.models import QuerySpec


def test_serialize_think_trace_contains_only_allowed_keys() -> None:
    trace = ExecutionTrace(
        intent=Intent.FILTER.value,
        product_families=[ProductFamily.ETF_KR.value],
        selected_retrievers=["SQL"],
        candidate_counts={"final": 1},
        decision_state="ANSWER",
        reason_codes=[ReasonCode.EVIDENCE_READY.value],
        dataset_version="2026-07-11-baseline",
        external_manifest_hash="abc",
        elapsed_ms=10,
        query_hash="hash",
    )
    payload = json.loads(serialize_think_trace(trace))
    assert set(payload) <= ALLOWED_TRACE_KEYS


def test_build_execution_trace_from_run_result() -> None:
    spec = QuerySpec(intent=Intent.FILTER, product_families=[ProductFamily.ETF_KR])
    run = AgentRunResult(
        query_id="q-1",
        spec=spec,
        execution_plan=None,
        merged_result=None,
        sql_result=None,
        relation_result=None,
        document_result=None,
        preliminary_decision=Decision(state=DecisionState.ASK, reason_codes=[]),
        evidence_requirements=[],
        trace_events=[],
    )
    trace = build_execution_trace(
        run,
        dataset_version="2026-07-11-baseline",
        external_manifest_hash=None,
        elapsed_ms=5,
        decision_state="ASK",
        reason_codes=[ReasonCode.MISSING_FILTERS],
    )
    assert trace.intent == Intent.FILTER.value
    assert trace.elapsed_ms == 5
