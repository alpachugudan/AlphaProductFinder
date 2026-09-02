from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


class SourceKeyError(ValueError):
    pass


def _normalize_key_part(value: Any) -> str:
    if value is None:
        raise SourceKeyError("source key field must not be empty")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return str(int(value))
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        raise SourceKeyError("source key field must not be empty")
    return text


def build_source_key(fields: list[str], payload: dict[str, Any]) -> str:
    """원천 키 직렬화 — 필드 순서 고정, 구분자 | 사용"""
    if not fields:
        msg = "source_key_fields must not be empty"
        raise SourceKeyError(msg)
    parts: list[str] = []
    for field in fields:
        if field not in payload:
            msg = f"missing source key field: {field}"
            raise SourceKeyError(msg)
        parts.append(_normalize_key_part(payload[field]))
    return "|".join(parts)
