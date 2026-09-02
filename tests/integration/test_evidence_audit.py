from __future__ import annotations

import json

from app.evidence.audit import AuditWriter, ExecutionLog, RequestLog
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_audit_writer_persists_without_secrets(db_session: Session) -> None:
    writer = AuditWriter()
    writer.write(
        db_session,
        request_id="req-001",
        question_hash="abc123",
        decision_state="ANSWER",
        elapsed_ms=12,
        llm_call_count=1,
        query_hash="query-hash",
        spec_summary={"intent": "FILTER", "filter_count": 1},
        selected_retrievers=["SQL"],
        candidate_counts={"final": 1},
        selected_source_keys=["PREF01N001:1"],
        evidence_hash="evidence-hash",
        model_name="mock",
        dataset_version="2026-07-11-baseline",
        external_manifest_hash=None,
    )

    request = db_session.scalar(select(RequestLog).where(RequestLog.request_id == "req-001"))
    execution = db_session.scalar(
        select(ExecutionLog).where(ExecutionLog.request_id == "req-001")
    )
    assert request is not None
    assert execution is not None
    assert request.question_hash == "abc123"
    assert execution.prompt_version == "mock-v1"

    serialized = json.dumps(
        {
            "request": {
                "question_hash": request.question_hash,
                "decision_state": request.decision_state,
            },
            "execution": {
                "spec_summary": execution.spec_summary,
                "model_name": execution.model_name,
            },
        }
    )
    assert "api_key" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert "system prompt" not in serialized.lower()
