from __future__ import annotations

import time

from app.data.repositories import ProductRepository, aggregate_numeric
from app.query.enums import Intent
from app.query.models import QuerySpec
from app.query.registry import get_field_registry
from app.query.validator import validate_queryspec_or_raise
from app.retrieval.federated_merger import build_retrieval_result, merge_cross_family
from app.retrieval.filter_compiler import build_safe_plan
from app.retrieval.models import RetrievalContext, RetrievalResult


class SqlRetriever:
    def __init__(self, repository: ProductRepository | None = None) -> None:
        self._repository = repository or ProductRepository()

    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        return self.retrieve_sync(spec, context)

    def retrieve_sync(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        started = time.perf_counter()
        registry = get_field_registry()
        validate_queryspec_or_raise(spec, registry)
        plan = build_safe_plan(spec, registry)
        session = context.session
        batches = []
        for family in plan.product_families:
            batch = self._repository.query(
                session,
                family=family,
                plan=plan,
                dataset_version_id=context.dataset_version_id,
                registry=registry,
            )
            batches.append(batch)

        if spec.intent == Intent.CROSS_FAMILY_SEARCH:
            metric = plan.metrics[0] if len(plan.metrics) == 1 else None
            candidates = merge_cross_family(
                batches,
                families=plan.product_families,
                limit=plan.limit,
                comparable_metric=metric,
            )
        else:
            candidates = []
            for batch in batches:
                candidates.extend(batch.candidates)
            candidates = candidates[: plan.limit]

        aggregate_value = None
        aggregate_op = None
        if spec.intent == Intent.AGGREGATE and plan.metrics:
            aggregate_op = "AVG"
            aggregate_value = aggregate_numeric(
                session,
                family=plan.product_families[0],
                plan=plan,
                dataset_version_id=context.dataset_version_id,
                field=plan.metrics[0],
                op=aggregate_op,
                registry=registry,
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return build_retrieval_result(
            spec=spec,
            plan=plan,
            batches=batches,
            candidates=candidates,
            elapsed_ms=elapsed_ms,
            aggregate_value=aggregate_value,
            aggregate_op=aggregate_op,
        )
