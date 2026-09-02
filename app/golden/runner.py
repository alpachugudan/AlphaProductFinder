from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import PROJECT_ROOT, Settings
from app.data.raw_models import DatasetVersion, DatasetVersionStatus
from app.evidence.answer_service import AgentAnswerResult, AgentAnswerService
from app.external.ingestion import MANIFEST_PATH, compute_manifest_hash
from app.query.models import QuerySpec
from app.retrieval.models import RetrievalContext

GOLDEN_PATH = PROJECT_ROOT / "tests" / "golden" / "questions.yaml"
EXPECTED_CASE_COUNT = 50


class GoldenConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GoldenCase:
    case_id: str
    axis: str
    question: str
    spec: QuerySpec
    expect: dict[str, Any]


@dataclass(slots=True)
class GoldenCaseResult:
    case_id: str
    axis: str
    question_sha256: str
    elapsed_ms: int
    passed: bool
    failures: list[str]
    decision: str | None = None
    reason_codes: list[str] | None = None
    candidate_count: int = 0
    evidence_hash_present: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "axis": self.axis,
            "question_sha256": self.question_sha256,
            "elapsed_ms": self.elapsed_ms,
            "passed": self.passed,
            "failures": self.failures,
            "decision": self.decision,
            "reason_codes": self.reason_codes or [],
            "candidate_count": self.candidate_count,
            "evidence_hash_present": self.evidence_hash_present,
        }


def load_golden_cases(path: Path = GOLDEN_PATH) -> list[GoldenCase]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise GoldenConfigurationError("golden YAML must contain a cases list")

    rows = payload["cases"]
    if len(rows) != EXPECTED_CASE_COUNT:
        raise GoldenConfigurationError(
            f"golden case count must be {EXPECTED_CASE_COUNT}, got {len(rows)}"
        )

    cases: list[GoldenCase] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise GoldenConfigurationError("golden case must be a mapping")
        if row.get("known_gap"):
            raise GoldenConfigurationError(
                f"release golden case cannot retain known_gap: {row.get('id', '<unknown>')}"
            )
        case_id_raw = row.get("id")
        axis_raw = row.get("axis")
        question_raw = row.get("question")
        expect = row.get("expect")
        if not all(isinstance(value, str) for value in (case_id_raw, axis_raw, question_raw)):
            raise GoldenConfigurationError("id, axis, and question must be strings")
        case_id = cast(str, case_id_raw)
        axis = cast(str, axis_raw)
        question = cast(str, question_raw)
        if case_id in seen:
            raise GoldenConfigurationError(f"duplicate golden id: {case_id}")
        if not isinstance(expect, dict):
            raise GoldenConfigurationError(f"expect must be a mapping: {case_id}")
        seen.add(case_id)
        cases.append(
            GoldenCase(
                case_id=case_id,
                axis=axis,
                question=question,
                spec=QuerySpec.model_validate(row.get("query_spec")),
                expect=expect,
            )
        )
    return cases


async def run_cases(
    *,
    session: Session,
    settings: Settings,
    cases: list[GoldenCase],
) -> list[GoldenCaseResult]:
    dataset = session.scalar(
        select(DatasetVersion).where(DatasetVersion.status == DatasetVersionStatus.ACTIVE.value)
    )
    if dataset is None:
        raise GoldenConfigurationError("active dataset version not found")

    context = RetrievalContext(
        dataset_version_id=dataset.id,
        dataset_version_label=dataset.version,
        session=session,
        external_version=compute_manifest_hash(MANIFEST_PATH) if MANIFEST_PATH.exists() else "none",
    )
    service = AgentAnswerService(settings=settings)
    results: list[GoldenCaseResult] = []
    for case in cases:
        started = time.perf_counter()
        try:
            answer = await service.answer_with_spec(
                case.spec, question=case.question, context=context
            )
        except Exception as exc:  # record every failed gate rather than hiding a case crash
            results.append(
                GoldenCaseResult(
                    case_id=case.case_id,
                    axis=case.axis,
                    question_sha256=_hash_question(case.question),
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    passed=False,
                    failures=[f"execution_error:{exc.__class__.__name__}"],
                )
            )
            continue
        results.append(
            evaluate_case(
                case,
                answer,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        )
    return results


def evaluate_case(
    case: GoldenCase, answer: AgentAnswerResult, *, elapsed_ms: int
) -> GoldenCaseResult:
    failures: list[str] = []
    spec = answer.run.spec
    expected_intent = case.expect.get("intent")
    expected_families = case.expect.get("families")
    expected_decision = case.expect.get("decision")
    expected_codes = {str(item) for item in case.expect.get("reason_codes", [])}
    actual_codes = {item.value for item in answer.final_decision.reason_codes}
    candidate_count = len(answer.final_decision.selected_candidate_ids)

    if spec.intent.value != expected_intent:
        failures.append(f"intent:{spec.intent.value}!={expected_intent}")
    if [item.value for item in spec.product_families] != expected_families:
        failures.append("families_mismatch")
    if answer.final_decision.state.value != expected_decision:
        failures.append(f"decision:{answer.final_decision.state.value}!={expected_decision}")
    if not expected_codes.issubset(actual_codes):
        failures.append("reason_codes_missing:" + ",".join(sorted(expected_codes - actual_codes)))

    minimum = case.expect.get("min_candidates")
    if isinstance(minimum, int) and candidate_count < minimum:
        failures.append(f"candidate_count:{candidate_count}<{minimum}")
    if not answer.guard_result.passed:
        failures.append("answer_guard_failed")
    if not answer.answer_text.lstrip().startswith(f"{answer.final_decision.state.value}:"):
        failures.append("answer_state_prefix_invalid")
    if "buyable_quantity" in answer.retrieved_context:
        failures.append("forbidden_buyable_quantity_evidence")

    if answer.final_decision.state.value == "ANSWER":
        has_relation_only = "[RELATION|" in answer.retrieved_context
        if candidate_count and not answer.evidence_hash:
            failures.append("candidate_answer_missing_evidence_hash")
        if not candidate_count and not has_relation_only:
            failures.append("answer_without_candidate_or_relation_evidence")
    else:
        if answer.retrieved_context != "meta=empty;original_count=0":
            failures.append("non_answer_must_not_expose_candidate_context")

    return GoldenCaseResult(
        case_id=case.case_id,
        axis=case.axis,
        question_sha256=_hash_question(case.question),
        elapsed_ms=elapsed_ms,
        passed=not failures,
        failures=failures,
        decision=answer.final_decision.state.value,
        reason_codes=sorted(actual_codes),
        candidate_count=candidate_count,
        evidence_hash_present=bool(answer.evidence_hash),
    )


def report_payload(
    *,
    provider: str,
    cases: list[GoldenCaseResult],
    dataset_version: str,
    external_manifest_hash: str,
) -> dict[str, object]:
    passed = sum(1 for item in cases if item.passed)
    return {
        "schema_version": "golden-report-1.0",
        "provider": provider,
        "dataset_version": dataset_version,
        "external_manifest_hash": external_manifest_hash,
        "case_count": len(cases),
        "passed_count": passed,
        "failed_count": len(cases) - passed,
        "all_passed": passed == len(cases),
        "cases": [item.as_dict() for item in cases],
    }


def write_report(payload: dict[str, object], directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = directory / f"golden-{stamp}.json"
    markdown_path = directory / f"golden-{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return json_path, markdown_path


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        "# Golden E2E Report",
        "",
        f"- provider: `{payload['provider']}`",
        f"- dataset_version: `{payload['dataset_version']}`",
        f"- cases: {payload['passed_count']}/{payload['case_count']} passed",
        "- raw questions and answer/evidence bodies are not written to this report.",
        "",
        "| ID | Axis | Result | ms | Decision | Candidates | Failures |",
        "|---|---|---:|---:|---|---:|---|",
    ]
    cases = payload.get("cases")
    assert isinstance(cases, list)
    for row_raw in cases:
        assert isinstance(row_raw, dict)
        row = row_raw
        failures = ", ".join(str(value) for value in row["failures"]) or "-"
        lines.append(
            (
                "| {case_id} | {axis} | {result} | {elapsed} | {decision} | "
                "{candidates} | {failures} |"
            ).format(
                case_id=row["case_id"],
                axis=row["axis"],
                result="PASS" if row["passed"] else "FAIL",
                elapsed=row["elapsed_ms"],
                decision=row["decision"] or "-",
                candidates=row["candidate_count"],
                failures=failures,
            )
        )
    return "\n".join(lines) + "\n"


def run_cases_sync(
    *, session: Session, settings: Settings, cases: list[GoldenCase]
) -> list[GoldenCaseResult]:
    return asyncio.run(run_cases(session=session, settings=settings, cases=cases))


def _hash_question(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()
