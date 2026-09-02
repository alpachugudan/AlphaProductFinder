from __future__ import annotations

import argparse
import json

from app.config.logging import configure_logging
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.external.coverage import build_coverage_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report external knowledge coverage")
    parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    session = get_session_factory()()
    try:
        report = build_coverage_report(session)
    finally:
        session.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
