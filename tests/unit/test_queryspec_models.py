from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.query.enums import Intent, Operator, ProductFamily
from app.query.models import FilterClause, QuerySpec
from app.query.registry import get_field_registry
from app.query.validator import validate_queryspec
from pydantic import ValidationError

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "queryspec"


def test_fixture_roundtrip() -> None:
    for path in FIXTURE_DIR.glob("*.json"):
        if path.name == "questions.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        spec = QuerySpec.model_validate(payload)
        assert spec.version == "1.0"


def test_extra_field_rejected() -> None:
    payload = json.loads((FIXTURE_DIR / "bond_remaining_days.json").read_text(encoding="utf-8"))
    payload["sql"] = "SELECT 1"
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(payload)


def test_limit_out_of_range() -> None:
    payload = json.loads((FIXTURE_DIR / "bond_remaining_days.json").read_text(encoding="utf-8"))
    payload["limit"] = 0
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(payload)
    payload["limit"] = 11
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(payload)


def test_between_requires_two_values() -> None:
    clause = FilterClause(field="remaining_days", operator=Operator.BETWEEN, value=[1])
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.BOND_KR],
        filters=[clause],
    )
    assert "INVALID_FILTER_VALUE_SHAPE" in {
        issue.code for issue in validate_queryspec(spec, get_field_registry())
    }


def test_null_operators_reject_value() -> None:
    clause = FilterClause(field="remaining_days", operator=Operator.IS_NULL, value=1)
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.BOND_KR],
        filters=[clause],
    )
    assert "FILTER_VALUE_MUST_BE_EMPTY" in {
        issue.code for issue in validate_queryspec(spec, get_field_registry())
    }


def test_json_schema_snapshot() -> None:
    schema = QuerySpec.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "intent" in schema["properties"]


def test_unsupported_prediction_allows_empty_families() -> None:
    spec = QuerySpec(
        intent=Intent.UNSUPPORTED_PREDICTION,
        product_families=[],
    )
    assert spec.intent == Intent.UNSUPPORTED_PREDICTION
