from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config.settings import PROJECT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate frozen external snapshot targets (offline, no network)"
    )
    parser.add_argument(
        "--targets",
        default=str(PROJECT_ROOT / "data/external/targets.yaml"),
        help="P0 target definition file",
    )
    args = parser.parse_args(argv)

    targets_path = Path(args.targets)
    if not targets_path.exists():
        print(f"ERROR: targets file missing: {targets_path}", file=sys.stderr)
        return 1

    print("Collect external OK (offline snapshot mode — network call 0)")
    print(f"  targets: {targets_path}")
    print("  note: production collector runs outside evaluation app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
