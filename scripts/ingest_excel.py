from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.config.logging import configure_logging
from app.config.settings import PROJECT_ROOT, get_settings
from app.data.ingestion import IngestionError, ingest_manifest
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest validated Excel files into PostgreSQL Raw layer"
    )
    parser.add_argument("--manifest", required=True, help="Path to source_manifest.json")
    parser.add_argument(
        "--source-dir",
        default=None,
        help="Directory containing Excel files (default: Settings SOURCE_DATA_DIR)",
    )
    parser.add_argument(
        "--skip-hash",
        action="store_true",
        help="Skip SHA-256 verification (tests only)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = (PROJECT_ROOT / manifest_path).resolve()
    source_dir = Path(args.source_dir) if args.source_dir else settings.resolved_source_data_dir()

    session = get_session_factory()()
    try:
        dataset_version = ingest_manifest(
            session,
            manifest_path,
            source_dir,
            verify_hashes=not args.skip_hash,
        )
    except (IngestionError, Exception) as exc:
        logger.exception("ingestion failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    print("Ingestion OK")
    print(f"  dataset_version: {dataset_version.version}")
    print(f"  status: {dataset_version.status}")
    print(f"  actual_row_count: {dataset_version.actual_row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
