from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.query.enums import ProductFamily
from app.query.registry import FieldRegistry, get_field_registry
from app.retrieval.column_map import get_product_model, resolve_column
from app.retrieval.filter_compiler import compile_filters
from app.retrieval.models import (
    Candidate,
    CandidateBatch,
    ExclusionCount,
    MetricReference,
    SafeQueryPlan,
)
from app.retrieval.ranking import sort_candidates


class ProductRepository:
    def query(
        self,
        session: Session,
        *,
        family: ProductFamily,
        plan: SafeQueryPlan,
        dataset_version_id: int,
        product_uids: list[str] | None = None,
        registry: FieldRegistry | None = None,
    ) -> CandidateBatch:
        registry = registry or get_field_registry()
        model = get_product_model(family)
        base_stmt = select(model).where(model.dataset_version_id == dataset_version_id)
        count_stmt = select(func.count()).select_from(model).where(
            model.dataset_version_id == dataset_version_id
        )
        if product_uids is not None:
            if not product_uids:
                return CandidateBatch(
                    family=family,
                    candidates=[],
                    count_before_filter=0,
                    count_after_filter=0,
                    count_after_quality=0,
                )
            base_stmt = base_stmt.where(model.product_uid.in_(product_uids))
            count_stmt = count_stmt.where(model.product_uid.in_(product_uids))
        count_before = session.scalar(count_stmt) or 0

        filters = compile_filters(family, plan.filters, registry)
        stmt = base_stmt
        for expression in filters:
            stmt = stmt.where(expression)
        rows = session.scalars(stmt.order_by(model.source_key)).all()
        count_after_filter = len(rows)

        metric_fields = list(dict.fromkeys([*plan.metrics, *[s.logical_field for s in plan.sorts]]))
        candidates: list[Candidate] = []
        quality_excluded = 0
        for row in rows:
            flags = list(row.quality_flags or [])
            candidate = Candidate(
                product_uid=row.product_uid,
                product_family=family,
                source_table=row.source_table,
                source_key=row.source_key,
                product_name=row.product_name,
                quality_flags=flags,
                tie_break_key=row.source_key,
            )
            for field in metric_fields:
                try:
                    column = resolve_column(family, field, registry)
                    raw_value = getattr(row, column.key)
                except KeyError:
                    continue
                # 결측 metric을 Evidence에 빈 문자열로 넣으면 원천값이 없는 사실을
                # 값처럼 보이게 한다. 요청 metric 중 실제 값이 있는 것만 근거로 남긴다.
                if raw_value is None:
                    continue
                field_def = registry.get(field)
                source_field = field_def.families[family].source_field if field_def else field
                metric_flags: list[str] = []
                if raw_value == 0 and "INVALID_FOR_DECISION" in flags:
                    # 0/sentinel 판정은 원천 row의 quality flag를 보존한다. 단순한 0을
                    # 매수가능 수량으로 오해하지 않으며, 해당 값만으로 후보를 답하지 않는다.
                    metric_flags.extend(["ZERO_VALUE", "INVALID_FOR_DECISION"])
                candidate.metrics_used.append(
                    MetricReference(
                        logical_field=field,
                        source_field=source_field,
                        raw_value=raw_value,
                        quality_flags=metric_flags,
                    )
                )
            candidates.append(candidate)

        use_pareto = len(plan.sorts) > 1 and all(item.priority is None for item in plan.sorts)
        ranked = sort_candidates(candidates, plan.sorts, use_pareto=use_pareto)
        if plan.sorts:
            sort_fields = {item.logical_field for item in plan.sorts}
            ranked = [
                item
                for item in ranked
                if all(
                    any(
                        metric.logical_field == field
                        and metric.raw_value is not None
                        and "INVALID_FOR_DECISION" not in metric.quality_flags
                        for metric in item.metrics_used
                    )
                    for field in sort_fields
                )
            ]
            quality_excluded = len(candidates) - len(ranked)

        final = ranked[: plan.limit]
        exclusions = []
        if quality_excluded:
            exclusions.append(
                ExclusionCount(reason_code="MISSING_RANK_METRIC", count=quality_excluded)
            )

        return CandidateBatch(
            family=family,
            candidates=final,
            count_before_filter=int(count_before),
            count_after_filter=count_after_filter,
            count_after_quality=len(ranked),
            exclusions=exclusions,
        )


def aggregate_numeric(
    session: Session,
    *,
    family: ProductFamily,
    plan: SafeQueryPlan,
    dataset_version_id: int,
    field: str,
    op: str,
    registry: FieldRegistry | None = None,
) -> Decimal | None:
    registry = registry or get_field_registry()
    model = get_product_model(family)
    column = resolve_column(family, field, registry)
    filters = compile_filters(family, plan.filters, registry)
    stmt = select(column).where(model.dataset_version_id == dataset_version_id)
    for expression in filters:
        stmt = stmt.where(expression)
    stmt = stmt.where(column.is_not(None))
    values = session.scalars(stmt).all()
    if not values:
        return None
    decimals = [Decimal(str(value)) for value in values]
    if op == "MIN":
        return min(decimals)
    if op == "MAX":
        return max(decimals)
    if op == "AVG":
        return sum(decimals) / Decimal(len(decimals))
    if op == "COUNT":
        return Decimal(len(decimals))
    msg = f"unsupported aggregate op: {op}"
    raise ValueError(msg)
