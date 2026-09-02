from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config.settings import PROJECT_ROOT, Settings
from app.data.raw_models import DatasetVersion, DatasetVersionStatus
from app.db.session import get_session_factory
from app.external.ingestion import MANIFEST_PATH, compute_manifest_hash
from app.golden.runner import (
    GOLDEN_PATH,
    GoldenConfigurationError,
    load_golden_cases,
    report_payload,
    run_cases_sync,
    write_report,
)
from sqlalchemy import select


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Step 11 Golden E2E suite")
    parser.add_argument("--provider", choices=["mock", "hyperclova"], default="mock")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--golden-path", type=Path, default=GOLDEN_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=PROJECT_ROOT / "artifacts" / "golden")
    parser.add_argument(
        "--allow-billable-hcx",
        action="store_true",
        help="required for HyperCLOVA execution; this can consume CLOVA Studio credits",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.provider == "hyperclova" and not args.allow_billable_hcx:
        print("REFUSED: HyperCLOVA Golden run requires --allow-billable-hcx", file=sys.stderr)
        return 2

    try:
        cases = load_golden_cases(args.golden_path)
    except GoldenConfigurationError as exc:
        print(f"CONFIG_ERROR: {exc}", file=sys.stderr)
        return 2
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.case_id in selected]
        if not cases or selected != {case.case_id for case in cases}:
            print("CONFIG_ERROR: unknown --case id", file=sys.stderr)
            return 2

    # Mock Golden은 외부 호출 없이 oracle QuerySpec부터 Answer Guard까지 검증한다.
    settings = Settings(app_env="development", llm_provider=args.provider)
    session = get_session_factory()()
    try:
        dataset = session.scalar(
            select(DatasetVersion).where(DatasetVersion.status == DatasetVersionStatus.ACTIVE.value)
        )
        if dataset is None:
            print("CONFIG_ERROR: active dataset version not found", file=sys.stderr)
            return 2
        results = run_cases_sync(session=session, settings=settings, cases=cases)
        report = report_payload(
            provider=args.provider,
            cases=results,
            dataset_version=dataset.version,
            external_manifest_hash=(
                compute_manifest_hash(MANIFEST_PATH) if MANIFEST_PATH.exists() else "none"
            ),
        )
    finally:
        session.close()

    json_path, markdown_path = write_report(report, args.artifacts_dir)
    print(
        "Golden result: {passed}/{total} passed; json={json}; markdown={markdown}".format(
            passed=report["passed_count"],
            total=report["case_count"],
            json=json_path,
            markdown=markdown_path,
        )
    )
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
