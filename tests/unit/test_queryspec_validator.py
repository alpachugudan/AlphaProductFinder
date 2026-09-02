from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.query.enums import Direction, Intent, Operator, ProductFamily
from app.query.models import PreferenceClause, QuerySpec, SortClause
from app.query.registry import get_field_registry
from app.query.validator import validate_queryspec
from pydantic import ValidationError

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "queryspec"
REGISTRY = get_field_registry()


def test_valid_fixtures_pass_semantic_validation() -> None:
    for path in FIXTURE_DIR.glob("*.json"):
        if path.name == "questions.json":
            continue
        spec = QuerySpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
        issues = validate_queryspec(spec, REGISTRY)
        assert issues == [], [issue.message for issue in issues]


def test_unknown_field_rejected() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.BOND_KR],
        filters=[{"field": "buyable_quantity", "operator": Operator.GTE, "value": 1}],
    )
    issues = validate_queryspec(spec, REGISTRY)
    assert any(issue.code == "UNKNOWN_FIELD" for issue in issues)


def test_operator_not_allowed_for_string_field() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "product_name", "operator": Operator.GTE, "value": "A"}],
    )
    issues = validate_queryspec(spec, REGISTRY)
    assert any(issue.code == "OPERATOR_NOT_ALLOWED" for issue in issues)


def test_field_not_supported_for_family() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.BOND_KR],
        filters=[{"field": "expense_ratio", "operator": Operator.LTE, "value": 1.0}],
    )
    issues = validate_queryspec(spec, REGISTRY)
    assert any(issue.code == "FIELD_NOT_SUPPORTED_FOR_FAMILY" for issue in issues)


def test_nav_discount_rank_blocked() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER_AND_RANK,
        product_families=[ProductFamily.ETF_GLOBAL],
        filters=[{"field": "investment_region", "operator": Operator.EQ, "value": "미국"}],
        preferences=[PreferenceClause(field="nav_discount", direction=Direction.DESC)],
    )
    issues = validate_queryspec(spec, REGISTRY)
    assert any(issue.code == "RANK_BLOCKED_FIELD" for issue in issues)


def test_etf_kr_expense_ratio_partial_coverage_metadata() -> None:
    field = REGISTRY.get("expense_ratio")
    assert field is not None
    mapping = field.families[ProductFamily.ETF_KR]
    assert mapping.coverage == "partial"


def test_sql_like_filter_value_rejected() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.BOND_KR],
        filters=[{"field": "product_name", "operator": Operator.CONTAINS, "value": "ABC;DROP"}],
    )
    issues = validate_queryspec(spec, REGISTRY)
    assert any(issue.code == "UNSAFE_VALUE" for issue in issues)


def test_sort_preference_conflict_detected_at_model_level() -> None:
    with pytest.raises(ValidationError):
        QuerySpec(
            intent=Intent.FILTER_AND_RANK,
            product_families=[ProductFamily.ETF_KR],
            filters=[{"field": "investment_region", "operator": Operator.EQ, "value": "미국"}],
            sort=[SortClause(field="expense_ratio", direction=Direction.ASC)],
            preferences=[PreferenceClause(field="expense_ratio", direction=Direction.DESC)],
        )


def test_unsupported_prediction_rejects_executable_clauses() -> None:
    spec = QuerySpec(
        intent=Intent.UNSUPPORTED_PREDICTION,
        product_families=[],
        filters=[{"field": "product_name", "operator": Operator.EQ, "value": "X"}],
    )
    issues = validate_queryspec(spec, REGISTRY)
    assert any(issue.code == "UNSUPPORTED_PREDICTION_NOT_EXECUTABLE" for issue in issues)
