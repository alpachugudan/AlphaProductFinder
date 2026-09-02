from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

from pythonjsonlogger.json import JsonFormatter

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """로그 레코드에 correlation_id 주입"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "-"
        return True


def configure_logging(level: str) -> None:
    """JSON 포맷 로깅 초기화 — UTF-8 한글 지원"""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(correlation_id)s",
            json_ensure_ascii=False,
        )
    )
    handler.addFilter(CorrelationIdFilter())
    root.addHandler(handler)


def bind_correlation_id(correlation_id: str) -> Any:
    """요청별 correlation ID 바인딩 — Step 08 감사 로그 확장 지점"""
    return correlation_id_var.set(correlation_id)


def reset_correlation_id(token: Any) -> None:
    correlation_id_var.reset(token)
