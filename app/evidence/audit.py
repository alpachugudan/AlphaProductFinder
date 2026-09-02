from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base


class RequestLog(Base):
    __tablename__ = "request_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_state: Mapped[str] = mapped_column(String(32), nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ExecutionLog(Base):
    __tablename__ = "execution_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    selected_retrievers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    candidate_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    selected_source_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    external_manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditWriter:
    """감사 로그 — 실패해도 답변 경로를 중단하지 않음"""

    PROMPT_VERSION = "mock-v1"

    def write(
        self,
        session: Session,
        *,
        request_id: str,
        question_hash: str,
        decision_state: str,
        elapsed_ms: int,
        llm_call_count: int,
        query_hash: str,
        spec_summary: dict[str, object],
        selected_retrievers: list[str],
        candidate_counts: dict[str, int],
        selected_source_keys: list[str],
        evidence_hash: str,
        model_name: str,
        dataset_version: str,
        external_manifest_hash: str | None,
        error_code: str | None = None,
    ) -> None:
        existing = session.scalar(
            select(RequestLog.id).where(RequestLog.request_id == request_id)
        )
        if existing is not None:
            return
        now = datetime.now(UTC)
        session.add(
            RequestLog(
                request_id=request_id,
                question_hash=question_hash,
                completed_at=now,
                decision_state=decision_state,
                elapsed_ms=elapsed_ms,
                llm_call_count=llm_call_count,
                error_code=error_code,
            )
        )
        session.add(
            ExecutionLog(
                request_id=request_id,
                query_hash=query_hash,
                spec_summary=spec_summary,
                selected_retrievers=selected_retrievers,
                candidate_counts=candidate_counts,
                selected_source_keys=selected_source_keys,
                evidence_hash=evidence_hash,
                model_name=model_name,
                prompt_version=self.PROMPT_VERSION,
                dataset_version=dataset_version,
                external_manifest_hash=external_manifest_hash,
            )
        )
        session.commit()
