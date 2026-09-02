from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AnswerResponse(BaseModel):
    """대회 평가기가 소비하는 고정 5-string JSON 계약."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    retrieved_context: str
    think_trace: str
    answer: str


class ReadyHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    checked_at: str
    components: dict[str, str]
