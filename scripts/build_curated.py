from __future__ import annotations

import argparse
import logging
import sys

from app.config.logging import configure_logging
from app.config.settings import get_settings
from app.curated.builder import CurationError, build_curated
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build curated/search layer from Raw data")
    parser.add_argument("--dataset-version", required=True, help="Active dataset version label")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    session = get_session_factory()()
    try:
        curation_run = build_curated(session, args.dataset_version)
    except CurationError as exc:
        logger.exception("curation failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    print("Curation OK")
    print(f"  dataset_version: {args.dataset_version}")
    print(f"  status: {curation_run.status}")
    print(f"  row_counts: {curation_run.row_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
