from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.query.enums import Direction
from app.retrieval.models import Candidate, SafeSort


def _metric_value(candidate: Candidate, field: str) -> Decimal | None:
    for metric in candidate.metrics_used:
        if metric.logical_field == field and metric.raw_value is not None:
            try:
                return Decimal(str(metric.raw_value))
            except Exception:
                return None
    return None


def sort_candidates(
    candidates: list[Candidate],
    sorts: list[SafeSort],
    *,
    use_pareto: bool = False,
) -> list[Candidate]:
    if not candidates or not sorts:
        return candidates

    if any(sort.priority is not None for sort in sorts):
        ordered = sorted(
            sorts,
            key=lambda item: item.priority if item.priority is not None else 10_000,
        )
        return _lexicographic_sort(candidates, ordered)

    if use_pareto and len(sorts) > 1 and all(item.priority is None for item in sorts):
        return pareto_select(candidates, sorts)

    return _lexicographic_sort(candidates, sorts)


def _lexicographic_sort(candidates: list[Candidate], sorts: list[SafeSort]) -> list[Candidate]:
    def sort_key(candidate: Candidate) -> tuple[Any, ...]:
        keys: list[Any] = []
        for sort in sorts:
            value = _metric_value(candidate, sort.logical_field)
            if value is None:
                keys.append(1 if sort.direction == Direction.ASC else 0)
                keys.append(0)
                continue
            keys.append(0)
            numeric = float(value)
            keys.append(numeric if sort.direction == Direction.ASC else -numeric)
        keys.append(candidate.tie_break_key or candidate.source_key)
        return tuple(keys)

    ranked = sorted(candidates, key=sort_key)
    for index, candidate in enumerate(ranked, start=1):
        candidate.stable_rank = index
        if not candidate.selection_reasons:
            candidate.selection_reasons.append("LEXICOGRAPHIC_SORT")
    return ranked


def dominates(a: Candidate, b: Candidate, sorts: list[SafeSort]) -> bool:
    not_worse_all = True
    better_any = False
    for sort in sorts:
        av = _metric_value(a, sort.logical_field)
        bv = _metric_value(b, sort.logical_field)
        if av is None or bv is None:
            return False
        if sort.direction == Direction.ASC:
            if av > bv:
                not_worse_all = False
            if av < bv:
                better_any = True
        else:
            if av < bv:
                not_worse_all = False
            if av > bv:
                better_any = True
    return not_worse_all and better_any


def pareto_frontier(candidates: list[Candidate], sorts: list[SafeSort]) -> list[Candidate]:
    eligible = [
        candidate
        for candidate in candidates
        if all(_metric_value(candidate, sort.logical_field) is not None for sort in sorts)
    ]
    frontier: list[Candidate] = []
    for candidate in eligible:
        dominated = any(
            other is not candidate and dominates(other, candidate, sorts) for other in eligible
        )
        if not dominated:
            frontier.append(candidate)
    frontier.sort(key=lambda item: item.tie_break_key or item.source_key)
    for candidate in frontier:
        candidate.selection_reasons.append("PARETO_FRONTIER")
    return frontier


def pareto_select(candidates: list[Candidate], sorts: list[SafeSort]) -> list[Candidate]:
    frontier = pareto_frontier(candidates, sorts)
    return _lexicographic_sort(frontier, sorts)
