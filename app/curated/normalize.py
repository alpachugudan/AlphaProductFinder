from __future__ import annotations

from datetime import date, datetime
from typing import Any


def normalize_product_name(name: Any) -> str | None:
    if name is None:
        return None
    text = str(name).strip()
    if not text:
        return None
    return " ".join(text.lower().split())


def raw_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_as_of_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text or text == "99991231":
        return None
    if len(text) == 8 and text.isdigit():
        return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
    if len(text) >= 10 and text[4] == "-":
        return date.fromisoformat(text[:10])
    return None
