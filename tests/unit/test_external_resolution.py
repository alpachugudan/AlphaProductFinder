from __future__ import annotations

from app.external.resolution import normalize_alias


def test_normalize_alias_collapses_whitespace() -> None:
    assert normalize_alias("  Samsung   Electronics ") == "samsung electronics"
