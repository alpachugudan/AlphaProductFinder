from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx

from app.config.settings import Settings
from app.core.deadline import get_request_deadline
from app.llm.errors import (
    HcxAuthenticationError,
    HcxConfigurationError,
    HcxRateLimitError,
    HcxResponseError,
    HcxTimeoutError,
    HcxUnavailableError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HcxUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class HcxCompletion:
    content: str
    model: str
    request_id: str
    usage: HcxUsage
    latency_ms: int
    retries: int


class HcxHttpClient:
    """HCX v3 호출 공통부. 비밀과 prompt 원문은 절대 로그에 기록하지 않는다."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def complete(self, *, model: str, payload: dict[str, Any]) -> HcxCompletion:
        api_key = self._require_api_key()
        self._ensure_billing_authorized()
        url = f"{self._settings.hcx_base_url}/v3/chat-completions/{model}"

        for attempt in range(self._settings.hcx_max_retries + 1):
            request_id = str(uuid4())
            started = monotonic()
            try:
                timeout = self._timeout_for_current_deadline()
                async with httpx.AsyncClient(
                    timeout=timeout,
                    transport=self._transport,
                    trust_env=False,
                ) as client:
                    response = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "X-NCP-CLOVASTUDIO-REQUEST-ID": request_id,
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                if await self._retry_or_stop(attempt, None):
                    continue
                raise HcxTimeoutError() from exc
            except httpx.HTTPError as exc:
                if await self._retry_or_stop(attempt, None):
                    continue
                raise HcxUnavailableError() from exc

            if response.status_code in {401, 403}:
                raise HcxAuthenticationError()
            if response.status_code == 429:
                if await self._retry_or_stop(attempt, response.headers.get("Retry-After")):
                    continue
                raise HcxRateLimitError()
            if 500 <= response.status_code <= 599:
                if await self._retry_or_stop(attempt, response.headers.get("Retry-After")):
                    continue
                raise HcxUnavailableError()
            if response.status_code >= 400:
                raise HcxResponseError()

            completion = self._parse_completion(
                response,
                model=model,
                request_id=request_id,
                latency_ms=int((monotonic() - started) * 1000),
                retries=attempt,
            )
            logger.info(
                "HCX request completed",
                extra={
                    "model": model,
                    "latency_ms": completion.latency_ms,
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "retries": attempt,
                },
            )
            return completion

        raise HcxUnavailableError()  # pragma: no cover - loop always returns or raises

    def _require_api_key(self) -> str:
        if self._settings.hcx_api_key is None:
            raise HcxConfigurationError("HCX_API_KEY is required for LLM_PROVIDER=hyperclova")
        value = self._settings.hcx_api_key.get_secret_value().strip()
        if not value:
            raise HcxConfigurationError("HCX_API_KEY is required for LLM_PROVIDER=hyperclova")
        return value

    def _ensure_billing_authorized(self) -> None:
        if (
            self._settings.billing_mode == "credit_only"
            and not self._settings.credit_balance_confirmed
        ):
            raise HcxConfigurationError(
                "credit_only mode blocks HCX calls until CREDIT_BALANCE_CONFIRMED=true"
            )

    def _timeout_for_current_deadline(self) -> httpx.Timeout:
        connect = self._settings.hcx_connect_timeout_seconds
        read = self._settings.hcx_read_timeout_seconds
        deadline = get_request_deadline()
        if deadline is not None:
            remaining = deadline.remaining_seconds()
            if remaining <= 0:
                raise HcxTimeoutError()
            connect = min(connect, remaining)
            read = min(read, remaining)
        return httpx.Timeout(connect=connect, read=read, write=read, pool=connect)

    async def _retry_or_stop(self, attempt: int, retry_after: str | None) -> bool:
        if attempt >= self._settings.hcx_max_retries:
            return False
        delay = _retry_delay(attempt, retry_after)
        deadline = get_request_deadline()
        if deadline is not None and deadline.remaining_seconds() <= delay + 0.05:
            return False
        await asyncio.sleep(delay)
        return True

    @staticmethod
    def _parse_completion(
        response: httpx.Response,
        *,
        model: str,
        request_id: str,
        latency_ms: int,
        retries: int,
    ) -> HcxCompletion:
        try:
            body = response.json()
            if body.get("status", {}).get("code") != "20000":
                raise ValueError("non-success NCP status")
            result = body["result"]
            content = result["message"]["content"]
            usage_raw = result.get("usage") or {}
            usage = HcxUsage(
                prompt_tokens=int(usage_raw.get("promptTokens", 0)),
                completion_tokens=int(usage_raw.get("completionTokens", 0)),
                total_tokens=int(usage_raw.get("totalTokens", 0)),
            )
        except (KeyError, TypeError, ValueError):
            raise HcxResponseError() from None
        if not isinstance(content, str) or not content.strip():
            raise HcxResponseError()
        return HcxCompletion(
            content=content,
            model=model,
            request_id=request_id,
            usage=usage,
            latency_ms=latency_ms,
            retries=retries,
        )


def _retry_delay(attempt: int, retry_after: str | None) -> float:
    if retry_after is not None:
        try:
            parsed_delay: float = float(retry_after)
            return min(max(parsed_delay, 0.0), 2.0)
        except ValueError:
            pass
    return float(0.15 * (2**attempt))
