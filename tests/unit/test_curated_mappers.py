from __future__ import annotations

from app.curated.mappers import map_fund_public, should_include_fund_public
from app.curated.product_family import ProductFamily
from app.data.raw_models import RawFund


def _raw_fund(payload: dict[str, object]) -> RawFund:
    row = RawFund()
    row.id = 1
    row.dataset_version_id = 1
    row.source_table = "PRFD01N001"
    row.source_key = str(payload.get("itm_no"))
    row.payload = payload
    row.value_states = {key: "empty" for key in payload}
    return row


def test_public_fund_filter() -> None:
    public = {"itm_no": "100", "prvo_pbff_desc": "공모", "itm_nm": "테스트 공모"}
    private = {"itm_no": "200", "prvo_pbff_desc": "사모", "itm_nm": "테스트 사모"}
    assert should_include_fund_public(public) is True
    assert should_include_fund_public(private) is False
    assert map_fund_public(_raw_fund(public)) is not None
    assert map_fund_public(_raw_fund(private)) is None


def test_public_fund_wk1_metric_blocked() -> None:
    mapped = map_fund_public(
        _raw_fund(
            {
                "itm_no": "100",
                "prvo_pbff_desc": "공모",
                "itm_nm": "테스트",
                "fd_wk1_ern_r": None,
            }
        )
    )
    assert mapped is not None
    wk1 = next(m for m in mapped.metrics if m.source_field == "fd_wk1_ern_r")
    assert "FEATURE_NOT_AVAILABLE_FOR_MARKET" in wk1.quality_flags
    assert mapped.product["product_family"] == ProductFamily.FUND_PUBLIC.value
