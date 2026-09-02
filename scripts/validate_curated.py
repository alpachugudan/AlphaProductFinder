from __future__ import annotations

import argparse
import logging
import sys

from app.config.logging import configure_logging
from app.config.settings import get_settings
from app.curated.validator import CuratedValidationError, validate_curated
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate curated/search layer invariants")
    parser.add_argument("--dataset-version", required=True, help="Active dataset version label")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    session = get_session_factory()()
    try:
        report = validate_curated(session, args.dataset_version)
    except CuratedValidationError as exc:
        logger.exception("curated validation failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    print("Curated validation OK")
    print(f"  dataset_version: {report.dataset_version}")
    print(f"  row_counts: {report.row_counts}")
    print(f"  fund_private_skipped: {report.fund_private_skipped}")
    print(f"  flag_summary: {report.flag_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
