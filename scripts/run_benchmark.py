from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

from app.config.settings import PROJECT_ROOT, Settings
from app.data.raw_models import DatasetVersion, DatasetVersionStatus
from app.db.session import get_session_factory
from app.evidence.answer_service import AgentAnswerService
from app.external.ingestion import MANIFEST_PATH, compute_manifest_hash
from app.golden.runner import GOLDEN_PATH, load_golden_cases
from app.retrieval.models import RetrievalContext
from sqlalchemy import select


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Step 11 Golden E2E mock path")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--golden-path", type=Path, default=GOLDEN_PATH)
    parser.add_argument(
        "--artifacts-dir", type=Path, default=PROJECT_ROOT / "artifacts" / "benchmark"
    )
    return parser.parse_args()


async def _benchmark() -> dict[str, object]:
    args = parse_args()
    if args.runs < 1 or args.runs > 10:
        raise ValueError("--runs must be between 1 and 10")
    cases = load_golden_cases(args.golden_path)
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.case_id in selected]
        if not cases or selected != {case.case_id for case in cases}:
            raise ValueError("unknown --case id")

    settings = Settings(app_env="development", llm_provider="mock")
    session = get_session_factory()()
    try:
        dataset = session.scalar(
            select(DatasetVersion).where(DatasetVersion.status == DatasetVersionStatus.ACTIVE.value)
        )
        if dataset is None:
            raise ValueError("active dataset version not found")
        context = RetrievalContext(
            dataset_version_id=dataset.id,
            dataset_version_label=dataset.version,
            session=session,
            external_version=(
                compute_manifest_hash(MANIFEST_PATH) if MANIFEST_PATH.exists() else "none"
            ),
        )
        samples: list[dict[str, object]] = []
        for phase in ("cold", "warm"):
            service = AgentAnswerService(settings=settings)
            for run in range(args.runs):
                for case in cases:
                    if phase == "cold":
                        service = AgentAnswerService(settings=settings)
                    started = time.perf_counter()
                    result = await service.answer_with_spec(
                        case.spec, question=case.question, context=context
                    )
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    samples.append(
                        {
                            "phase": phase,
                            "run": run + 1,
                            "case_id": case.case_id,
                            "elapsed_ms": elapsed_ms,
                            "decision": result.final_decision.state.value,
                        }
                    )
        return {
            "schema_version": "benchmark-report-1.0",
            "provider": "mock",
            "dataset_version": dataset.version,
            "case_count": len(cases),
            "runs_per_phase": args.runs,
            "thresholds_ms": {"total_p50": 8000, "total_p95": 20000},
            "summary": _summarize(samples),
            "samples": samples,
        }
    finally:
        session.close()


def _summarize(samples: list[dict[str, object]]) -> dict[str, dict[str, int]]:
    grouped: dict[str, list[int]] = {"cold": [], "warm": []}
    for sample in samples:
        elapsed_ms = sample["elapsed_ms"]
        assert isinstance(elapsed_ms, int)
        grouped[str(sample["phase"])].append(elapsed_ms)
    return {phase: _percentiles(values) for phase, values in grouped.items()}


def _percentiles(values: list[int]) -> dict[str, int]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "p50_ms": 0, "p95_ms": 0, "max_ms": 0}
    return {
        "count": len(ordered),
        "p50_ms": ordered[math.ceil(len(ordered) * 0.50) - 1],
        "p95_ms": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "max_ms": ordered[-1],
    }


def _write_report(report: dict[str, object], directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = directory / f"benchmark-{stamp}.json"
    markdown_path = directory / f"benchmark-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "# Golden E2E Benchmark",
        "",
        "| Phase | Count | p50 ms | p95 ms | Max ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for phase in ("cold", "warm"):
        row = summary[phase]
        assert isinstance(row, dict)
        lines.append(
            f"| {phase} | {row['count']} | {row['p50_ms']} | {row['p95_ms']} | {row['max_ms']} |"
        )
    lines.extend(
        [
            "",
            "- threshold: total p50 <= 8,000 ms; total p95 <= 20,000 ms.",
            "- mock only; no financial evidence is sent to CLOVA Studio.",
            "- raw questions, answers, and retrieved evidence are excluded from this report.",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        report = asyncio.run(_benchmark())
    except ValueError as exc:
        print(f"CONFIG_ERROR: {exc}")
        return 2
    args = parse_args()
    json_path, markdown_path = _write_report(report, args.artifacts_dir)
    summary = report["summary"]
    assert isinstance(summary, dict)
    warm = summary["warm"]
    assert isinstance(warm, dict)
    passed = int(warm["p50_ms"]) <= 8000 and int(warm["p95_ms"]) <= 20000
    print(
        f"Benchmark result: warm p50={warm['p50_ms']}ms p95={warm['p95_ms']}ms; "
        f"json={json_path}; markdown={markdown_path}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
