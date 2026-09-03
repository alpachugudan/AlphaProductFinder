from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.config.settings import Settings
from app.llm.client import HcxCompletion, HcxHttpClient, HcxUsage
from app.llm.errors import HcxAuthenticationError, HcxConfigurationError
from app.llm.hyperclova_provider import HyperClovaProvider


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "app_env": "test",
        "llm_provider": "hyperclova",
        "hcx_api_key": "test-secret",
        "credit_balance_confirmed": True,
        "hcx_max_retries": 1,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _response(content: str = "{}") -> dict[str, object]:
    return {
        "status": {"code": "20000", "message": "OK"},
        "result": {
            "message": {"role": "assistant", "content": content},
            "usage": {"promptTokens": 11, "completionTokens": 7, "totalTokens": 18},
        },
    }


@pytest.mark.asyncio(loop_scope="module")
async def test_hcx_client_uses_v3_headers_and_parses_usage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["request_id"] = request.headers["X-NCP-CLOVASTUDIO-REQUEST-ID"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_response('{"intent":"UNSUPPORTED_PREDICTION"}'))

    client = HcxHttpClient(_settings(), transport=httpx.MockTransport(handler))
    completion = await client.complete(
        model="HCX-007",
        payload={"messages": [{"role": "system", "content": "schema"}]},
    )

    assert captured["url"] == "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-007"
    assert captured["authorization"] == "Bearer test-secret"
    assert isinstance(captured["request_id"], str)
    assert completion.usage == HcxUsage(11, 7, 18)


@pytest.mark.asyncio(loop_scope="module")
async def test_hcx_client_blocks_unconfirmed_credit_before_http() -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=_response())

    client = HcxHttpClient(
        _settings(credit_balance_confirmed=False),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(HcxConfigurationError):
        await client.complete(model="HCX-007", payload={"messages": []})
    assert called is False


@pytest.mark.asyncio(loop_scope="module")
async def test_hcx_client_retries_rate_limit_once() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=_response("ok"))

    client = HcxHttpClient(_settings(), transport=httpx.MockTransport(handler))
    result = await client.complete(model="HCX-007", payload={"messages": []})
    assert calls == 2
    assert result.retries == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_hcx_client_does_not_retry_authentication_failure() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"status": {"code": "401"}})

    client = HcxHttpClient(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(HcxAuthenticationError):
        await client.complete(model="HCX-007", payload={"messages": []})
    assert calls == 1


class StubHcxClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.payloads: list[dict[str, Any]] = []

    async def complete(self, *, model: str, payload: dict[str, Any]) -> HcxCompletion:
        self.payloads.append(payload)
        return HcxCompletion(
            content=self._responses.pop(0),
            model=model,
            request_id="test-request",
            usage=HcxUsage(1, 1, 2),
            latency_ms=1,
            retries=0,
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_hyperclova_provider_corrects_invalid_queryspec_once() -> None:
    fixture = Path("tests/fixtures/queryspec/etf_kr_expense_rank.json").read_text(
        encoding="utf-8"
    )
    stub = StubHcxClient(["not-json", fixture])
    provider = HyperClovaProvider(_settings(), client=stub)  # type: ignore[arg-type]

    spec = await provider.parse_query("국내 ETF 중 보수가 가장 낮은 상품 알려줘")

    assert spec.intent.value == "FILTER_AND_RANK"
    assert len(stub.payloads) == 2
    assert "failed JSON Schema validation" in stub.payloads[1]["messages"][1]["content"]
    first_body = stub.payloads[0]
    assert "responseFormat" in first_body
    assert first_body["thinking"] == {"effort": "none"}


@pytest.mark.asyncio(loop_scope="module")
async def test_hyperclova_provider_defers_semantic_queryspec_issues_to_policy() -> None:
    semantically_unsupported = json.dumps(
        {
            "version": "1.0",
            "intent": "FILTER",
            "product_families": ["BOND_KR"],
            "entities": [],
            "filters": [
                {"field": "investment_region", "operator": "CONTAINS", "value": "미국"}
            ],
            "relationship_filters": [],
            "metrics": [],
            "preferences": [],
            "sort": [],
            "limit": 5,
            "as_of_requirement": "SHOW_FIELD_DATE",
            "missing_policy": "EXCLUDE_AND_DISCLOSE",
        }
    )
    stub = StubHcxClient([semantically_unsupported])
    provider = HyperClovaProvider(_settings(), client=stub)  # type: ignore[arg-type]

    spec = await provider.parse_query("지원하지 않는 채권 조건 테스트")

    assert spec.filters[0].field == "investment_region"
    assert len(stub.payloads) == 1
