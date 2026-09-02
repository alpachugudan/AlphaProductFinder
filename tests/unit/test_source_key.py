from __future__ import annotations

import pytest
from app.data.source_key import SourceKeyError, build_source_key


def test_single_field_key() -> None:
    key = build_source_key(["pd_itm_no"], {"pd_itm_no": "KR123"})
    assert key == "KR123"


def test_composite_key_non_collision() -> None:
    key_a = build_source_key(
        ["pd_no", "pd_exg_mkt", "info_base_dt", "info_seq"],
        {"pd_no": "1", "pd_exg_mkt": "A", "info_base_dt": 20260821, "info_seq": 1},
    )
    key_b = build_source_key(
        ["pd_no", "pd_exg_mkt", "info_base_dt", "info_seq"],
        {"pd_no": "1|A", "pd_exg_mkt": "B", "info_base_dt": 20260821, "info_seq": 1},
    )
    assert key_a != key_b


def test_missing_key_field_raises() -> None:
    with pytest.raises(SourceKeyError):
        build_source_key(["pd_itm_no"], {"other": "x"})


def test_empty_key_field_raises() -> None:
    with pytest.raises(SourceKeyError):
        build_source_key(["pd_itm_no"], {"pd_itm_no": "  "})
