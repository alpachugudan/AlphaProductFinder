from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, cast

from app.config.settings import PROJECT_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Step 11 release gates from generated reports"
    )
    parser.add_argument("--golden-report", type=Path)
    parser.add_argument("--benchmark-report", type=Path)
    parser.add_argument(
        "--artifacts-dir", type=Path, default=PROJECT_ROOT / "artifacts" / "release-gate"
    )
    return parser.parse_args()


def _latest(directory: Path, prefix: str) -> Path:
    candidates = sorted(directory.glob(f"{prefix}-*.json"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        raise ValueError(f"no {prefix} report found in {directory}")
    return candidates[-1]


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"report root must be object: {path}")
    return cast(dict[str, Any], payload)


def _evaluate(golden: dict[str, Any], benchmark: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if golden.get("case_count") != 50:
        failures.append("golden_case_count_not_50")
    if golden.get("all_passed") is not True:
        failures.append("golden_not_all_passed")
    if golden.get("provider") != "mock":
        failures.append("golden_provider_must_be_mock_for_nonbillable_gate")

    summary = benchmark.get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("warm"), dict):
        failures.append("benchmark_warm_summary_missing")
        return failures
    warm = cast(dict[str, Any], summary["warm"])
    if int(warm.get("p50_ms", 999999)) > 8000:
        failures.append("benchmark_warm_p50_exceeds_8000ms")
    if int(warm.get("p95_ms", 999999)) > 20000:
        failures.append("benchmark_warm_p95_exceeds_20000ms")
    if int(warm.get("count", 0)) < 50:
        failures.append("benchmark_warm_sample_count_below_50")
    return failures


def _write_report(
    *,
    directory: Path,
    golden_path: Path,
    benchmark_path: Path,
    failures: list[str],
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    payload = {
        "schema_version": "release-gate-1.0",
        "passed": not failures,
        "failures": failures,
        "golden_report": golden_path.name,
        "benchmark_report": benchmark_path.name,
        "checks": [
            "Golden case count is exactly 50",
            "Golden mock report has no failures or known gaps",
            "Benchmark warm p50 <= 8000ms and p95 <= 20000ms",
            "No CLOVA Studio request is made by this gate",
        ],
    }
    json_path = directory / f"release-gate-{stamp}.json"
    markdown_path = directory / f"release-gate-{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = "PASS" if not failures else "FAIL"
    markdown_path.write_text(
        "# Step 11 Release Gate\n\n"
        f"- result: **{state}**\n"
        f"- golden: `{golden_path.name}`\n"
        f"- benchmark: `{benchmark_path.name}`\n"
        "- CLOVA Studio call: none (Mock only)\n"
        f"- failures: {', '.join(failures) if failures else 'none'}\n",
        encoding="utf-8",
    )
    return json_path, markdown_path


def main() -> int:
    args = parse_args()
    try:
        golden_path = args.golden_report or _latest(PROJECT_ROOT / "artifacts" / "golden", "golden")
        benchmark_path = args.benchmark_report or _latest(
            PROJECT_ROOT / "artifacts" / "benchmark", "benchmark"
        )
        failures = _evaluate(_load(golden_path), _load(benchmark_path))
        json_path, markdown_path = _write_report(
            directory=args.artifacts_dir,
            golden_path=golden_path,
            benchmark_path=benchmark_path,
            failures=failures,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"GATE_ERROR: {exc}")
        return 2
    print(
        f"Release gate: {'PASS' if not failures else 'FAIL'}; "
        f"json={json_path}; markdown={markdown_path}"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
