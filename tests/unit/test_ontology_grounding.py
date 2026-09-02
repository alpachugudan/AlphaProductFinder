from __future__ import annotations

import pytest
from app.query.enums import GroundingRule
from app.query.ontology_grounding import (
    AmbiguousGrounding,
    GroundingMatch,
    ground_token,
    normalize_token,
)


def test_normalize_token_nfkc_and_case() -> None:
    assert normalize_token("  보 수 ") == "보 수"
    assert normalize_token("AUM") == "aum"


def test_synonym_grounding_expense_ratio() -> None:
    result = ground_token("총보수")
    assert isinstance(result, GroundingMatch)
    assert result.canonical_id == "expense_ratio"
    assert result.rule == GroundingRule.SYNONYM


def test_ambiguous_grounding_when_alias_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.query.ontology_grounding as grounding_module

    monkeypatch.setattr(
        grounding_module,
        "_build_synonym_index",
        lambda: {"수익률": {"applied_yield", "return_1y"}},
    )
    result = ground_token("수익률")
    assert isinstance(result, AmbiguousGrounding)
    assert result.code == "AMBIGUOUS_GROUNDING"
    assert len(result.candidates) == 2
