from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeVar

from app.core.errors import RequestDeadlineExceeded

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RequestDeadline:
    """요청 전체에 적용되는 단조 시계 기반 마감 시각."""

    expires_at: float

    @classmethod
    def after(cls, timeout_seconds: float) -> RequestDeadline:
        return cls(expires_at=time.monotonic() + timeout_seconds)

    def remaining_seconds(self) -> float:
        return max(0.0, self.expires_at - time.monotonic())


_request_deadline: ContextVar[RequestDeadline | None] = ContextVar(
    "request_deadline", default=None
)


def get_request_deadline() -> RequestDeadline | None:
    """현재 요청의 deadline. Provider/Retry 구현(Step 10)이 이어받는 경계."""

    return _request_deadline.get()


async def run_with_deadline(
    operation: Awaitable[T], *, timeout_seconds: float
) -> T:
    """deadline을 context에 노출하고 초과 시 하위 coroutine을 취소한다."""

    deadline = RequestDeadline.after(timeout_seconds)
    token = _request_deadline.set(deadline)
    try:
        try:
            async with asyncio.timeout(deadline.remaining_seconds()):
                return await operation
        except TimeoutError as exc:
            raise RequestDeadlineExceeded() from exc
    finally:
        _request_deadline.reset(token)
