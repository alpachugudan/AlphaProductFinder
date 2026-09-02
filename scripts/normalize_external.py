from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config.settings import PROJECT_ROOT
from app.external.ingestion import NORMALIZED_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate normalized external snapshot files")
    parser.add_argument(
        "--manifest",
        default=str(PROJECT_ROOT / "data/external/manifests/external_manifest.yaml"),
    )
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ERROR: manifest missing: {manifest_path}", file=sys.stderr)
        return 1

    required = [
        "source_documents.jsonl",
        "entities.jsonl",
        "aliases.jsonl",
        "holdings.jsonl",
        "relations.jsonl",
        "document_chunks.jsonl",
    ]
    missing = [name for name in required if not (NORMALIZED_DIR / name).exists()]
    if missing:
        print(f"ERROR: normalized files missing: {missing}", file=sys.stderr)
        return 1

    print("Normalize external OK")
    print(f"  manifest: {manifest_path}")
    print(f"  normalized_dir: {NORMALIZED_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
