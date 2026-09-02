from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config.logging import configure_logging
from app.config.settings import PROJECT_ROOT, get_settings
from app.db.session import get_session_factory
from app.external.ingestion import ExternalIngestionError, ingest_external


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest frozen external knowledge snapshot")
    parser.add_argument(
        "--manifest",
        default="data/external/manifests/external_manifest.yaml",
        help="External manifest path relative to project root or absolute",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = PROJECT_ROOT / manifest_path

    session = get_session_factory()()
    try:
        run = ingest_external(session, manifest_path)
    except ExternalIngestionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    print("External ingestion OK")
    print(f"  manifest_hash: {run.manifest_hash}")
    print(f"  status: {run.status}")
    print(f"  row_counts: {run.row_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
