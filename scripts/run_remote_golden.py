from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from app.config.settings import PROJECT_ROOT

EXPECTED_RESPONSE_KEYS = {
    "question_id",
    "question",
    "retrieved_context",
    "think_trace",
    "answer",
}
GOLDEN_PATH = PROJECT_ROOT / "tests" / "golden" / "questions.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all Golden cases through deployed GET /answer"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--allow-billable-hcx", action="store_true")
    parser.add_argument("--timeout", type=float, default=130.0)
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "remote-golden",
    )
    return parser.parse_args()


def evaluate_case(
    *,
    case: dict[str, Any],
    response: httpx.Response,
    elapsed_ms: int,
) -> dict[str, object]:
    case_id = str(case["id"])
    expect = case["expect"]
    question = str(case["question"])
    result: dict[str, object] = {
        "case_id": case_id,
        "axis": str(case["axis"]),
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "status_code": response.status_code,
        "elapsed_ms": elapsed_ms,
        "passed": False,
        "failures": [],
        "decision": None,
    }
    failures: list[str] = []
    try:
        payload = response.json()
    except ValueError:
        failures.append("response_not_json")
        result["failures"] = failures
        return result
    if not isinstance(payload, dict) or set(payload) != EXPECTED_RESPONSE_KEYS:
        failures.append("response_schema_invalid")
        result["failures"] = failures
        return result
    if not all(isinstance(value, str) for value in payload.values()):
        failures.append("response_values_not_all_strings")
    if response.status_code != 200:
        failures.append(f"unexpected_status:{response.status_code}")
    if payload["question_id"] != case_id or payload["question"] != question:
        failures.append("question_echo_mismatch")
    try:
        trace = json.loads(payload["think_trace"])
    except (TypeError, ValueError):
        failures.append("think_trace_invalid_json")
        result["failures"] = failures
        return result
    if not isinstance(trace, dict):
        failures.append("think_trace_not_object")
        result["failures"] = failures
        return result
    decision = trace.get("decision_state")
    result["decision"] = decision if isinstance(decision, str) else None
    if decision != expect.get("decision"):
        failures.append(f"decision:{decision}!={expect.get('decision')}")
    if trace.get("intent") != expect.get("intent"):
        failures.append("intent_mismatch")
    if trace.get("product_families") != expect.get("families"):
        failures.append("families_mismatch")
    actual_codes = set(trace.get("reason_codes", []))
    expected_codes = set(expect.get("reason_codes", []))
    if not expected_codes.issubset(actual_codes):
        failures.append("reason_codes_missing")
    counts = trace.get("candidate_counts")
    minimum = expect.get("min_candidates")
    if isinstance(minimum, int) and (
        not isinstance(counts, dict)
        or not isinstance(counts.get("final"), int)
        or counts["final"] < minimum
    ):
        failures.append("candidate_count_below_minimum")
    if isinstance(decision, str) and not payload["answer"].startswith(f"{decision}:"):
        failures.append("answer_prefix_invalid")
    result["passed"] = not failures
    result["failures"] = failures
    return result


def main() -> int:
    args = parse_args()
    if not args.allow_billable_hcx:
        raise SystemExit("REFUSED: --allow-billable-hcx is required")
    payload = yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or len(cases) != 50:
        raise SystemExit("CONFIG_ERROR: expected exactly 50 Golden cases")

    base_url = args.base_url.rstrip("/")
    results: list[dict[str, object]] = []
    with httpx.Client(timeout=args.timeout, trust_env=False) as client:
        for case in cases:
            if not isinstance(case, dict):
                raise SystemExit("CONFIG_ERROR: Golden case must be an object")
            started = time.perf_counter()
            try:
                response = client.get(
                    f"{base_url}/answer",
                    params={"question_id": case["id"], "question": case["question"]},
                )
                result = evaluate_case(
                    case=case,
                    response=response,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                )
            except httpx.HTTPError as exc:
                result = {
                    "case_id": str(case["id"]),
                    "axis": str(case["axis"]),
                    "question_sha256": hashlib.sha256(
                        str(case["question"]).encode("utf-8")
                    ).hexdigest(),
                    "status_code": None,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "passed": False,
                    "failures": [f"request_error:{exc.__class__.__name__}"],
                    "decision": None,
                }
            results.append(result)
            print(
                "{case_id}: {status} {decision} {result}".format(
                    case_id=result["case_id"],
                    status=result["status_code"],
                    decision=result["decision"],
                    result="PASS" if result["passed"] else "FAIL",
                )
            )

    passed = sum(item["passed"] is True for item in results)
    report = {
        "schema_version": "remote-golden-report-1.0",
        "base_url": base_url,
        "case_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "all_passed": passed == len(results),
        "cases": results,
    }
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.artifacts_dir / f"remote-golden-{time.strftime('%Y%m%d-%H%M%S')}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Remote Golden result: {passed}/{len(results)} passed; report={report_path}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
