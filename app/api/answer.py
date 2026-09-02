from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.models import AnswerResponse
from app.config.settings import Settings
from app.core.deadline import run_with_deadline
from app.core.errors import SystemUnavailableError
from app.data.raw_models import DatasetVersion, DatasetVersionStatus
from app.evidence.answer_service import AgentAnswerService
from app.external.ingestion import MANIFEST_PATH, compute_manifest_hash
from app.llm.mock_provider import MockLlmError
from app.retrieval.models import RetrievalContext

router = APIRouter(tags=["evaluation"])


@dataclass(frozen=True, slots=True)
class AnswerPayload:
    retrieved_context: str
    think_trace: str
    answer: str


class AnswerExecutor(Protocol):
    async def execute(self, question: str) -> AnswerPayload: ...


class DefaultAnswerExecutor:
    """HTTP 계약과 Step 08 Agent service 사이의 DB context 경계."""

    def __init__(self, *, session_factory: object, service: AgentAnswerService) -> None:
        self._session_factory = cast(Callable[[], Session], session_factory)
        self._service = service

    async def execute(self, question: str) -> AnswerPayload:
        session = self._open_session()
        try:
            context = self._load_active_context(session)
            result = await self._service.answer_question(question, context)
        except SQLAlchemyError as exc:
            raise SystemUnavailableError("DATABASE_UNAVAILABLE") from exc
        finally:
            session.close()
        return AnswerPayload(
            retrieved_context=result.retrieved_context,
            think_trace=result.think_trace,
            answer=result.answer_text,
        )

    def _open_session(self) -> Session:
        try:
            return self._session_factory()
        except SQLAlchemyError as exc:
            raise SystemUnavailableError("DATABASE_UNAVAILABLE") from exc

    @staticmethod
    def _load_active_context(session: Session) -> RetrievalContext:
        dataset = session.scalar(
            select(DatasetVersion).where(DatasetVersion.status == DatasetVersionStatus.ACTIVE.value)
        )
        if dataset is None:
            raise SystemUnavailableError("ACTIVE_DATASET_UNAVAILABLE")
        external_version = (
            compute_manifest_hash(MANIFEST_PATH) if MANIFEST_PATH.exists() else "none"
        )
        return RetrievalContext(
            dataset_version_id=dataset.id,
            dataset_version_label=dataset.version,
            session=session,
            external_version=external_version,
        )


def get_answer_executor(request: Request) -> AnswerExecutor:
    existing = getattr(request.app.state, "answer_executor", None)
    if existing is not None:
        return cast(AnswerExecutor, existing)

    settings = cast(Settings, request.app.state.settings)
    executor = DefaultAnswerExecutor(
        session_factory=request.app.state.session_factory,
        service=AgentAnswerService(settings=settings),
    )
    request.app.state.answer_executor = executor
    return executor


def _input_ask_response(
    question_id: str, question: str, reason_code: str, answer: str
) -> AnswerResponse:
    return AnswerResponse(
        question_id=question_id,
        question=question,
        retrieved_context="",
        think_trace=json.dumps(
            {"decision_state": "ASK", "reason_code": reason_code},
            sort_keys=True,
            separators=(",", ":"),
        ),
        answer=answer,
    )


def _mock_abstain_response(question_id: str, question: str) -> AnswerResponse:
    return AnswerResponse(
        question_id=question_id,
        question=question,
        retrieved_context="",
        think_trace=json.dumps(
            {"decision_state": "ABSTAIN", "reason_code": "MOCK_QUESTION_UNAVAILABLE"},
            sort_keys=True,
            separators=(",", ":"),
        ),
        answer="ABSTAIN: 현재 개발용 Mock provider에는 이 질문의 검증 가능한 처리 규칙이 없습니다.",
    )


AnswerExecutorDep = Annotated[AnswerExecutor, Depends(get_answer_executor)]


@router.get("/answer", response_model=AnswerResponse)
async def answer(
    request: Request,
    executor: AnswerExecutorDep,
    question_id: str | None = None,
    question: str | None = None,
) -> AnswerResponse:
    """평가용 GET endpoint. 입력 부족과 답변 불가는 정상 200으로 처리한다."""

    preserved_question_id = question_id if question_id is not None else ""
    preserved_question = question if question is not None else ""
    settings = cast(Settings, request.app.state.settings)

    if not preserved_question.strip():
        return _input_ask_response(
            preserved_question_id,
            preserved_question,
            "MISSING_QUESTION",
            "ASK: 질문 내용을 입력해 주세요.",
        )
    if len(preserved_question) > settings.max_question_length:
        return _input_ask_response(
            preserved_question_id,
            preserved_question,
            "QUESTION_TOO_LONG",
            f"ASK: 질문은 {settings.max_question_length}자 이하로 입력해 주세요.",
        )

    try:
        payload = await run_with_deadline(
            executor.execute(preserved_question),
            timeout_seconds=settings.internal_timeout_seconds,
        )
    except MockLlmError:
        return _mock_abstain_response(preserved_question_id, preserved_question)

    return AnswerResponse(
        question_id=preserved_question_id,
        question=preserved_question,
        retrieved_context=payload.retrieved_context,
        think_trace=payload.think_trace,
        answer=payload.answer,
    )
