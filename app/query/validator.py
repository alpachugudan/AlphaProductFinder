from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.query.enums import Intent, Operator
from app.query.models import QuerySpec
from app.query.registry import FieldDefinition, FieldRegistry


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    json_path: str
    askable: bool
    details: dict[str, Any] = field(default_factory=dict)


class QuerySpecValidationError(Exception):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__(issues[0].message if issues else "validation failed")


SQL_INJECTION_MARKERS = (";", "SELECT", "DROP", "INSERT", "UPDATE", "DELETE", "--")


def validate_queryspec(spec: QuerySpec, registry: FieldRegistry) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_intent_shape(spec))
    issues.extend(_validate_fields_exist(spec, registry))
    issues.extend(_validate_family_support(spec, registry))
    issues.extend(_validate_operators_and_values(spec, registry))
    issues.extend(_validate_rank_blocked(spec, registry))
    issues.extend(_validate_sql_injection(spec))
    return issues


def validate_queryspec_or_raise(spec: QuerySpec, registry: FieldRegistry) -> None:
    issues = validate_queryspec(spec, registry)
    if issues:
        raise QuerySpecValidationError(issues)


def _validate_intent_shape(spec: QuerySpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if spec.intent == Intent.UNSUPPORTED_PREDICTION:
        has_executable = any(
            [
                spec.filters,
                spec.metrics,
                spec.preferences,
                spec.sort,
                spec.relationship_filters,
            ]
        )
        if has_executable:
            issues.append(
                ValidationIssue(
                    code="UNSUPPORTED_PREDICTION_NOT_EXECUTABLE",
                    message="UNSUPPORTED_PREDICTION must not include executable search clauses",
                    json_path="$.intent",
                    askable=False,
                )
            )
        return issues

    if spec.intent in {Intent.FILTER, Intent.FILTER_AND_RANK} and not spec.filters:
        issues.append(
            ValidationIssue(
                code="MISSING_FILTERS",
                message=f"{spec.intent} requires at least one filter",
                json_path="$.filters",
                askable=True,
            )
        )

    if spec.intent == Intent.FILTER_AND_RANK and not (
        spec.preferences or spec.sort or spec.metrics
    ):
        issues.append(
            ValidationIssue(
                code="MISSING_RANKING",
                message="FILTER_AND_RANK requires preferences, sort, or metrics",
                json_path="$.preferences",
                askable=True,
            )
        )

    if spec.intent == Intent.RELATION_SEARCH and not spec.relationship_filters:
        issues.append(
            ValidationIssue(
                code="MISSING_RELATIONSHIP_FILTERS",
                message="RELATION_SEARCH requires relationship_filters",
                json_path="$.relationship_filters",
                askable=True,
            )
        )

    if spec.intent == Intent.LOOKUP_PRODUCT and not (
        spec.entities or _has_product_name_filter(spec)
    ):
        issues.append(
            ValidationIssue(
                code="MISSING_LOOKUP_TARGET",
                message="LOOKUP_PRODUCT requires entities or product_name filter",
                json_path="$.entities",
                askable=True,
            )
        )

    return issues


def _has_product_name_filter(spec: QuerySpec) -> bool:
    return any(item.field == "product_name" for item in spec.filters)


def _validate_fields_exist(spec: QuerySpec, registry: FieldRegistry) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    referenced = _collect_field_refs(spec)
    for path, field_id in referenced:
        if registry.get(field_id) is None:
            issues.append(
                ValidationIssue(
                    code="UNKNOWN_FIELD",
                    message=f"unknown logical field: {field_id}",
                    json_path=path,
                    askable=False,
                    details={"field": field_id},
                )
            )
    return issues


def _collect_field_refs(spec: QuerySpec) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for idx, clause in enumerate(spec.filters):
        refs.append((f"$.filters[{idx}].field", clause.field))
    for idx, metric in enumerate(spec.metrics):
        refs.append((f"$.metrics[{idx}]", metric))
    for idx, pref in enumerate(spec.preferences):
        refs.append((f"$.preferences[{idx}].field", pref.field))
    for idx, sort in enumerate(spec.sort):
        refs.append((f"$.sort[{idx}].field", sort.field))
    return refs


def _validate_family_support(spec: QuerySpec, registry: FieldRegistry) -> list[ValidationIssue]:
    if spec.intent == Intent.UNSUPPORTED_PREDICTION:
        return []

    issues: list[ValidationIssue] = []
    families = spec.product_families
    for path, field_id in _collect_field_refs(spec):
        definition = registry.get(field_id)
        if definition is None:
            continue
        if not any(registry.supports_family(field_id, family) for family in families):
            issues.append(
                ValidationIssue(
                    code="FIELD_NOT_SUPPORTED_FOR_FAMILY",
                    message=f"field {field_id} is not supported for selected families",
                    json_path=path,
                    askable=True,
                    details={"field": field_id, "families": [f.value for f in families]},
                )
            )
    return issues


def _validate_operators_and_values(
    spec: QuerySpec, registry: FieldRegistry
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for idx, clause in enumerate(spec.filters):
        definition = registry.get(clause.field)
        if definition is None:
            continue
        if clause.operator not in definition.operators:
            issues.append(
                ValidationIssue(
                    code="OPERATOR_NOT_ALLOWED",
                    message=f"operator {clause.operator} not allowed for {clause.field}",
                    json_path=f"$.filters[{idx}].operator",
                    askable=True,
                )
            )
        if not definition.filterable:
            issues.append(
                ValidationIssue(
                    code="FIELD_NOT_FILTERABLE",
                    message=f"field {clause.field} is not filterable",
                    json_path=f"$.filters[{idx}].field",
                    askable=False,
                )
            )
        issues.extend(
            _validate_value_type(
                definition,
                clause.value,
                f"$.filters[{idx}].value",
                clause.operator,
            )
        )
    return issues


def _validate_value_type(
    definition: FieldDefinition,
    value: Any,
    json_path: str,
    operator: Operator,
) -> list[ValidationIssue]:
    if operator in {Operator.IS_NULL, Operator.NOT_NULL}:
        return []

    if operator == Operator.BETWEEN:
        values = value if isinstance(value, list) else []
        between_issues: list[ValidationIssue] = []
        for item in values:
            between_issues.extend(_validate_single_value(definition, item, json_path))
        return between_issues

    if operator == Operator.IN:
        values = value if isinstance(value, list) else []
        in_issues: list[ValidationIssue] = []
        for idx, item in enumerate(values):
            in_issues.extend(_validate_single_value(definition, item, f"{json_path}[{idx}]"))
        return in_issues

    return _validate_single_value(definition, value, json_path)


def _validate_single_value(
    definition: FieldDefinition, value: Any, json_path: str
) -> list[ValidationIssue]:
    if definition.value_type == "string":
        if not isinstance(value, str):
            return [
                ValidationIssue(
                    code="INVALID_VALUE_TYPE",
                    message=f"{definition.id} expects string",
                    json_path=json_path,
                    askable=True,
                )
            ]
        return []

    if definition.value_type in {"decimal", "integer"}:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return [
                ValidationIssue(
                    code="INVALID_VALUE_TYPE",
                    message=f"{definition.id} expects numeric value",
                    json_path=json_path,
                    askable=True,
                )
            ]
        return []

    if definition.value_type == "boolean":
        if not isinstance(value, bool):
            return [
                ValidationIssue(
                    code="INVALID_VALUE_TYPE",
                    message=f"{definition.id} expects boolean",
                    json_path=json_path,
                    askable=True,
                )
            ]
        return []

    return []


def _validate_rank_blocked(spec: QuerySpec, registry: FieldRegistry) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for idx, pref in enumerate(spec.preferences):
        definition = registry.get(pref.field)
        if definition and definition.rank_blocked:
            issues.append(
                ValidationIssue(
                    code="RANK_BLOCKED_FIELD",
                    message=f"field {pref.field} cannot be used for ranking",
                    json_path=f"$.preferences[{idx}].field",
                    askable=False,
                    details={"reason": "DATE_MISMATCH_POLICY"},
                )
            )
    for idx, sort in enumerate(spec.sort):
        definition = registry.get(sort.field)
        if definition and definition.rank_blocked:
            issues.append(
                ValidationIssue(
                    code="RANK_BLOCKED_FIELD",
                    message=f"field {sort.field} cannot be used for sorting",
                    json_path=f"$.sort[{idx}].field",
                    askable=False,
                )
            )
    return issues


def _validate_sql_injection(spec: QuerySpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for idx, clause in enumerate(spec.filters):
        if isinstance(clause.value, str):
            upper = clause.value.upper()
            if any(marker in upper for marker in SQL_INJECTION_MARKERS):
                issues.append(
                    ValidationIssue(
                        code="UNSAFE_VALUE",
                        message="filter value contains disallowed SQL-like tokens",
                        json_path=f"$.filters[{idx}].value",
                        askable=False,
                    )
                )
        if any(marker in clause.field.upper() for marker in SQL_INJECTION_MARKERS):
            issues.append(
                ValidationIssue(
                    code="UNSAFE_FIELD",
                    message="field name contains disallowed SQL-like tokens",
                    json_path=f"$.filters[{idx}].field",
                    askable=False,
                )
            )
    return issues
