from __future__ import annotations

import argparse
import json
import sys
import time

from app.data.raw_models import DatasetVersion, DatasetVersionStatus
from app.db.session import get_session_factory
from app.query.enums import Intent, Operator, ProductFamily
from app.query.models import QuerySpec
from app.retrieval.models import RetrievalContext
from app.retrieval.sql_retriever import SqlRetriever
from sqlalchemy import select


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark structured retrieval latency")
    parser.add_argument("--dataset-version", required=True)
    args = parser.parse_args(argv)

    session = get_session_factory()()
    try:
        version = session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.version == args.dataset_version,
                DatasetVersion.status == DatasetVersionStatus.ACTIVE.value,
            )
        )
        if version is None:
            print("ERROR: active dataset version not found", file=sys.stderr)
            return 1

        specs = [
            QuerySpec(
                intent=Intent.FILTER,
                product_families=[ProductFamily.BOND_KR],
                filters=[{"field": "remaining_days", "operator": Operator.LTE, "value": 365}],
            ),
            QuerySpec(
                intent=Intent.FILTER_AND_RANK,
                product_families=[ProductFamily.ETF_KR],
                filters=[
                    {"field": "investment_region", "operator": Operator.CONTAINS, "value": "미국"}
                ],
                preferences=[{"field": "expense_ratio", "direction": "ASC", "priority": 1}],
                metrics=["expense_ratio"],
            ),
        ]
        retriever = SqlRetriever()
        context = RetrievalContext(
            dataset_version_id=version.id,
            dataset_version_label=version.version,
            session=session,
        )
        timings: list[int] = []
        for spec in specs:
            start = time.perf_counter()
            result = retriever.retrieve_sync(spec, context)
            elapsed = int((time.perf_counter() - start) * 1000)
            timings.append(elapsed)
            print(f"  {spec.intent.value}: {elapsed}ms, final={result.count_final}")

        p95 = sorted(timings)[max(0, int(len(timings) * 0.95) - 1)]
        print(json.dumps({"p95_ms": p95, "samples": timings}))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
