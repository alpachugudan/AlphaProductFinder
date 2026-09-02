from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config.settings import PROJECT_ROOT, get_settings
from app.data.validator import ValidationFailedError, validate_or_raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate source Excel hashes and structure")
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to source_manifest.json",
    )
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

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = (PROJECT_ROOT / manifest_path).resolve()

    settings = get_settings()
    source_dir = Path(args.source_dir) if args.source_dir else settings.resolved_source_data_dir()

    try:
        result = validate_or_raise(
            manifest_path,
            source_dir,
            verify_hashes=not args.skip_hash,
        )
    except ValidationFailedError as exc:
        for error in exc.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Validation OK")
    for table, count in result.row_counts.items():
        print(f"  {table}: {count}")
    print(f"  TOTAL: {sum(result.row_counts.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
