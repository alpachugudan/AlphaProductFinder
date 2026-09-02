from __future__ import annotations

import re

from sqlalchemy import ColumnElement, and_

from app.query.enums import Operator, ProductFamily
from app.query.models import QuerySpec
from app.query.registry import FieldRegistry, get_field_registry
from app.retrieval.column_map import resolve_column
from app.retrieval.models import SafeFilter, SafeQueryPlan, SafeSort

LIKE_ESCAPE = re.compile(r"([\\%_])")


class FilterCompileError(ValueError):
    pass


def escape_like_pattern(value: str) -> str:
    return LIKE_ESCAPE.sub(r"\\\1", value)


def build_safe_plan(spec: QuerySpec, registry: FieldRegistry | None = None) -> SafeQueryPlan:
    registry = registry or get_field_registry()
    filters = [
        SafeFilter(logical_field=item.field, operator=item.operator, value=item.value)
        for item in spec.filters
    ]
    sorts: list[SafeSort] = []
    for pref in spec.preferences:
        field_def = registry.get(pref.field)
        if field_def and field_def.rank_blocked:
            msg = f"rank blocked field in preferences: {pref.field}"
            raise FilterCompileError(msg)
        sorts.append(
            SafeSort(logical_field=pref.field, direction=pref.direction, priority=pref.priority)
        )
    for item in spec.sort:
        field_def = registry.get(item.field)
        if field_def and field_def.rank_blocked:
            msg = f"rank blocked field in sort: {item.field}"
            raise FilterCompileError(msg)
        sorts.append(SafeSort(logical_field=item.field, direction=item.direction, priority=None))
    return SafeQueryPlan(
        product_families=list(spec.product_families),
        filters=filters,
        sorts=sorts,
        limit=spec.limit,
        metrics=list(spec.metrics),
    )


def compile_filter_expression(
    family: ProductFamily,
    clause: SafeFilter,
    registry: FieldRegistry | None = None,
) -> ColumnElement[bool]:
    registry = registry or get_field_registry()
    logical_field = clause.logical_field
    field_def = registry.get(logical_field)
    if field_def is None:
        msg = f"unknown field: {logical_field}"
        raise FilterCompileError(msg)
    if family not in field_def.families:
        msg = f"field {logical_field} unsupported for {family.value}"
        raise FilterCompileError(msg)
    if not field_def.filterable:
        msg = f"field not filterable: {logical_field}"
        raise FilterCompileError(msg)

    column = resolve_column(family, logical_field, registry)
    operator = clause.operator
    value = clause.value

    if operator == Operator.IS_NULL:
        return column.is_(None)
    if operator == Operator.NOT_NULL:
        return column.is_not(None)
    if operator == Operator.EQ:
        return column == value
    if operator == Operator.NE:
        return column != value
    if operator == Operator.GTE:
        return column >= value
    if operator == Operator.LTE:
        return column <= value
    if operator == Operator.IN:
        if not isinstance(value, list):
            msg = "IN requires list value"
            raise FilterCompileError(msg)
        return column.in_(value)
    if operator == Operator.BETWEEN:
        if not isinstance(value, list) or len(value) != 2:
            msg = "BETWEEN requires two values"
            raise FilterCompileError(msg)
        low, high = value
        return and_(column >= low, column <= high)
    if operator == Operator.CONTAINS:
        if not isinstance(value, str):
            msg = "CONTAINS requires string value"
            raise FilterCompileError(msg)
        pattern = f"%{escape_like_pattern(value)}%"
        return column.ilike(pattern, escape="\\")
    msg = f"unsupported operator: {operator}"
    raise FilterCompileError(msg)


def compile_filters(
    family: ProductFamily,
    filters: list[SafeFilter],
    registry: FieldRegistry | None = None,
) -> list[ColumnElement[bool]]:
    return [compile_filter_expression(family, item, registry) for item in filters]
