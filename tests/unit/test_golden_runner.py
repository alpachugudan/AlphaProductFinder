from __future__ import annotations

from pathlib import Path

import pytest
from app.golden.runner import EXPECTED_CASE_COUNT, GoldenConfigurationError, load_golden_cases


def test_golden_suite_has_50_unique_release_cases() -> None:
    cases = load_golden_cases()
    assert len(cases) == EXPECTED_CASE_COUNT
    assert len({case.case_id for case in cases}) == EXPECTED_CASE_COUNT
    assert {case.axis for case in cases} >= {
        "relation_holds",
        "future_prediction",
        "missing_zero_sentinel",
        "answer_guard",
    }


def test_golden_loader_rejects_known_gap(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        "cases:\n" + "".join(
            f"  - id: G-{index:03d}\n"
            "    axis: test\n"
            "    question: q\n"
            "    known_gap: true\n"
            "    query_spec: {intent: UNSUPPORTED_PREDICTION, product_families: []}\n"
            "    expect: {intent: UNSUPPORTED_PREDICTION, families: [], decision: ABSTAIN}\n"
            for index in range(1, EXPECTED_CASE_COUNT + 1)
        ),
        encoding="utf-8",
    )
    with pytest.raises(GoldenConfigurationError, match="known_gap"):
        load_golden_cases(path)
