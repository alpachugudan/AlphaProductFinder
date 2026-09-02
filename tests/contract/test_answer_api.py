from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
import pytest
from app.api.answer import AnswerPayload
from app.api.readiness import ReadinessSnapshot
from app.config.settings import Settings
from app.core.errors import RetrieverFailure
from app.llm.mock_provider import MockLlmError
from app.main import create_app
from fastapi import FastAPI

pytestmark = pytest.mark.asyncio(loop_scope="module")

EXPECTED_KEYS = {
    "question_id",
    "question",
    "retrieved_context",
    "think_trace",
    "answer",
}


@dataclass
class StubExecutor:
    payload: AnswerPayload = AnswerPayload(
        retrieved_context="source=fixture",
        think_trace='{"decision_state":"ANSWER"}',
        answer="ANSWER: fixture response",
    )
    error: Exception | None = None
    calls: int = 0

    async def execute(self, _: str) -> AnswerPayload:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.payload


@dataclass
class StubReadiness:
    snapshot: ReadinessSnapshot

    async def check(self) -> ReadinessSnapshot:
        return self.snapshot


def _application(
    executor: StubExecutor | None = None,
    *,
    timeout_seconds: int = 120,
    readiness: StubReadiness | None = None,
) -> FastAPI:
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost:5432/test_db",
        llm_provider="mock",
        internal_timeout_seconds=timeout_seconds,
    )
    application = create_app(lambda: settings)
    application.state.answer_executor = executor or StubExecutor()
    application.state.readiness_service = readiness or StubReadiness(
        ReadinessSnapshot(
            ready=True,
            checked_at="2026-09-02T00:00:00+00:00",
            components={
                "database": "ok",
                "migration": "ok",
                "dataset": "ok",
                "ontology_registry": "ok",
                "llm_provider": "ok",
            },
        )
    )
    return application


def _assert_contract(response: httpx.Response, *, question_id: str, question: str) -> None:
    data = response.json()
    assert response.status_code in {200, 503}
    assert response.headers["content-type"].startswith("application/json")
    assert set(data) == EXPECTED_KEYS
    assert all(isinstance(value, str) for value in data.values())
    assert data["question_id"] == question_id
    assert data["question"] == question


async def test_answer_exact_five_string_contract_and_url_decoding() -> None:
    question = "미국 ETF & 수수료+낮은% (비교)"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_application()), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/answer",
            params={"question_id": "Q-한글 1", "question": question, "unused": "ignored"},
        )

    _assert_contract(response, question_id="Q-한글 1", question=question)
    assert response.json()["answer"].startswith("ANSWER:")


async def test_answer_and_ask_and_abstain_are_all_200() -> None:
    cases = [
        StubExecutor(payload=AnswerPayload("ctx", "trace", "ANSWER: ok")),
        StubExecutor(payload=AnswerPayload("", "trace", "ASK: more detail")),
        StubExecutor(payload=AnswerPayload("", "trace", "ABSTAIN: unavailable")),
    ]
    for executor in cases:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_application(executor)), base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/answer", params={"question_id": "Q-001", "question": "질문"}
            )
        _assert_contract(response, question_id="Q-001", question="질문")
        assert response.status_code == 200


async def test_missing_or_blank_input_is_safe_200_without_execution() -> None:
    executor = StubExecutor()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_application(executor)), base_url="http://testserver"
    ) as client:
        missing = await client.get("/answer")
        blank = await client.get(
            "/answer", params={"question_id": "Q-002", "question": "   "}
        )

    _assert_contract(missing, question_id="", question="")
    _assert_contract(blank, question_id="Q-002", question="   ")
    assert missing.json()["answer"].startswith("ASK:")
    assert blank.json()["answer"].startswith("ASK:")
    assert executor.calls == 0


async def test_missing_question_id_is_preserved_as_empty_string() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_application()), base_url="http://testserver"
    ) as client:
        response = await client.get("/answer", params={"question": "질문"})

    _assert_contract(response, question_id="", question="질문")


async def test_mock_unknown_question_is_domain_abstain_not_5xx() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=_application(StubExecutor(error=MockLlmError("unknown question")))
        ),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/answer", params={"question_id": "Q-003", "question": "미등록"}
        )

    _assert_contract(response, question_id="Q-003", question="미등록")
    assert response.status_code == 200
    assert response.json()["answer"].startswith("ABSTAIN:")


async def test_system_failure_is_503_without_internal_detail() -> None:
    secret = "postgresql://name:secret@db/internal"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=_application(StubExecutor(error=RetrieverFailure("SQL", secret)))
        ),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/answer", params={"question_id": "Q-004", "question": "질문"}
        )

    _assert_contract(response, question_id="Q-004", question="질문")
    assert response.status_code == 503
    assert "RETRIEVER_FAILURE" in response.json()["think_trace"]
    assert secret not in response.text
    assert "Traceback" not in response.text


async def test_internal_deadline_cancels_execution() -> None:
    class SlowExecutor:
        cancelled = False

        async def execute(self, _: str) -> AnswerPayload:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            raise AssertionError("unreachable")

    executor = SlowExecutor()
    started = time.perf_counter()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_application(executor, timeout_seconds=1)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/answer", params={"question_id": "Q-005", "question": "질문"}
        )
    elapsed = time.perf_counter() - started

    _assert_contract(response, question_id="Q-005", question="질문")
    assert response.status_code == 503
    assert "REQUEST_DEADLINE_EXCEEDED" in response.json()["think_trace"]
    assert executor.cancelled is True
    assert elapsed < 2.0


async def test_post_answer_is_not_a_normal_evaluation_route() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_application()), base_url="http://testserver"
    ) as client:
        response = await client.post("/answer", json={"question": "질문"})

    assert response.status_code == 405


async def test_openapi_exposes_only_the_fixed_get_answer_contract() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_application()), base_url="http://testserver"
    ) as client:
        schema = (await client.get("/openapi.json")).json()

    assert set(schema["paths"]["/answer"]) == {"get"}
    operation = schema["paths"]["/answer"]["get"]
    parameters = {item["name"]: item["required"] for item in operation["parameters"]}
    assert parameters == {"question_id": False, "question": False}
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    answer_schema = schema["components"]["schemas"][response_schema["$ref"].rsplit("/", 1)[-1]]
    assert list(answer_schema["properties"]) == [
        "question_id",
        "question",
        "retrieved_context",
        "think_trace",
        "answer",
    ]
    assert answer_schema["required"] == list(answer_schema["properties"])
    assert answer_schema["additionalProperties"] is False


async def test_repeated_request_is_side_effect_free_at_api_boundary() -> None:
    executor = StubExecutor()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_application(executor)), base_url="http://testserver"
    ) as client:
        first = await client.get("/answer", params={"question_id": "Q-006", "question": "질문"})
        second = await client.get("/answer", params={"question_id": "Q-006", "question": "질문"})

    assert first.json() == second.json()
    assert executor.calls == 2


async def test_readiness_is_distinct_from_liveness_and_has_no_sensitive_fields() -> None:
    readiness = StubReadiness(
        ReadinessSnapshot(
            ready=False,
            checked_at="2026-09-02T00:00:00+00:00",
            components={"database": "unavailable", "migration": "outdated"},
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_application(readiness=readiness)),
        base_url="http://testserver",
    ) as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert set(ready.json()) == {"status", "checked_at", "components"}
    assert "password" not in ready.text.lower()
