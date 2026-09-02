from __future__ import annotations

import json

from app.agent.orchestrator import AgentRunResult
from app.agent.reason_codes import ReasonCode
from app.evidence.models import ExecutionTrace

ALLOWED_TRACE_KEYS = frozenset(
    {
        "intent",
        "product_families",
        "selected_retrievers",
        "candidate_counts",
        "decision_state",
        "reason_codes",
        "dataset_version",
        "external_manifest_hash",
        "elapsed_ms",
        "query_hash",
    }
)


def build_execution_trace(
    run: AgentRunResult,
    *,
    dataset_version: str,
    external_manifest_hash: str | None,
    elapsed_ms: int,
    decision_state: str,
    reason_codes: list[ReasonCode],
) -> ExecutionTrace:
    selected_retrievers: list[str] = []
    if run.execution_plan is not None:
        selected_retrievers = [item.kind.value for item in run.execution_plan.retrievers]

    candidate_counts = {
        "before_filter": run.merged_result.count_before_filter if run.merged_result else 0,
        "after_filter": run.merged_result.count_after_filter if run.merged_result else 0,
        "final": run.merged_result.count_final if run.merged_result else 0,
    }
    query_hash = run.execution_plan.spec_hash if run.execution_plan else ""
    return ExecutionTrace(
        intent=run.spec.intent.value,
        product_families=[family.value for family in run.spec.product_families],
        selected_retrievers=selected_retrievers,
        candidate_counts=candidate_counts,
        decision_state=decision_state,
        reason_codes=[code.value for code in reason_codes],
        dataset_version=dataset_version,
        external_manifest_hash=external_manifest_hash,
        elapsed_ms=elapsed_ms,
        query_hash=query_hash,
    )


def serialize_think_trace(trace: ExecutionTrace) -> str:
    payload = {
        "candidate_counts": trace.candidate_counts,
        "dataset_version": trace.dataset_version,
        "decision_state": trace.decision_state,
        "elapsed_ms": trace.elapsed_ms,
        "external_manifest_hash": trace.external_manifest_hash,
        "intent": trace.intent,
        "product_families": trace.product_families,
        "query_hash": trace.query_hash,
        "reason_codes": trace.reason_codes,
        "selected_retrievers": trace.selected_retrievers,
    }
    if set(payload) - ALLOWED_TRACE_KEYS:
        msg = "think_trace contains disallowed keys"
        raise ValueError(msg)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
