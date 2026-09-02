from __future__ import annotations

import pytest
from app.query.enums import Direction, Operator, ProductFamily
from app.query.models import QuerySpec
from app.retrieval.filter_compiler import (
    FilterCompileError,
    build_safe_plan,
    compile_filter_expression,
)
from app.retrieval.models import Candidate, MetricReference, SafeFilter, SafeSort
from app.retrieval.ranking import pareto_frontier, sort_candidates


def test_build_safe_plan_rejects_rank_blocked_field() -> None:
    spec = QuerySpec(
        intent="FILTER_AND_RANK",
        product_families=[ProductFamily.ETF_GLOBAL],
        filters=[{"field": "investment_region", "operator": "EQ", "value": "미국"}],
        preferences=[{"field": "nav_discount", "direction": "DESC"}],
    )
    with pytest.raises(FilterCompileError):
        build_safe_plan(spec)


def test_contains_escapes_wildcards() -> None:
    expr = compile_filter_expression(
        ProductFamily.ETF_KR,
        SafeFilter(
            logical_field="product_name",
            operator=Operator.CONTAINS,
            value="100%_test",
        ),
    )
    assert expr is not None


def test_pareto_frontier_selects_nondominated() -> None:
    candidates = [
        Candidate(
            product_uid="A",
            product_family=ProductFamily.ETF_KR,
            source_table="PREF01N001",
            source_key="a",
            product_name="A",
            tie_break_key="a",
            metrics_used=[
                MetricReference("expense_ratio", "cu_charge_rt", 0.1),
                MetricReference("aum", "du_last_aum", 100),
            ],
        ),
        Candidate(
            product_uid="B",
            product_family=ProductFamily.ETF_KR,
            source_table="PREF01N001",
            source_key="b",
            product_name="B",
            tie_break_key="b",
            metrics_used=[
                MetricReference("expense_ratio", "cu_charge_rt", 0.2),
                MetricReference("aum", "du_last_aum", 200),
            ],
        ),
    ]
    sorts = [
        SafeSort("expense_ratio", Direction.ASC),
        SafeSort("aum", Direction.DESC),
    ]
    frontier = pareto_frontier(candidates, sorts)
    assert len(frontier) == 2

    ranked = sort_candidates(candidates, sorts, use_pareto=True)
    assert ranked
