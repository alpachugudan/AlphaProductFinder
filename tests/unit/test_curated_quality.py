from __future__ import annotations

from app.curated.product_family import ProductFamily
from app.curated.product_uid import build_product_uid
from app.curated.quality import QualityFlag, assess_metric


def test_bond_product_uid_is_stable_hash() -> None:
    payload = {
        "pd_no": "KR123",
        "pd_exg_mkt": "KRX",
        "info_base_dt": "20250711",
        "info_seq": 1,
    }
    uid = build_product_uid(ProductFamily.BOND_KR, payload, "ignored")
    assert uid.startswith("BOND_KR:")
    assert build_product_uid(ProductFamily.BOND_KR, payload, "other") == uid


def test_etf_and_fund_uids() -> None:
    assert (
        build_product_uid(ProductFamily.ETF_KR, {"pd_itm_no": "A001"}, "k")
        == "ETF_KR:A001"
    )
    assert (
        build_product_uid(ProductFamily.ETF_GLOBAL, {"pd_itm_no": "G001"}, "k")
        == "ETF_GLOBAL:G001"
    )
    assert (
        build_product_uid(ProductFamily.FUND_PUBLIC, {"itm_no": "F001"}, "k")
        == "FUND_PUBLIC:F001"
    )


def test_buyable_quantity_is_invalid_for_decision() -> None:
    assessment = assess_metric(
        source_field="buyable_quantity",
        value=10,
        value_state=None,
    )
    assert QualityFlag.INVALID_FOR_DECISION.value in assessment.quality_flags


def test_fd_wk1_ern_r_is_feature_unavailable() -> None:
    assessment = assess_metric(
        source_field="fd_wk1_ern_r",
        value=None,
        value_state="empty",
    )
    flags = assessment.quality_flags
    assert QualityFlag.FEATURE_NOT_AVAILABLE_FOR_MARKET.value in flags
    assert QualityFlag.MISSING.value in flags


def test_zero_value_flag() -> None:
    assessment = assess_metric(
        source_field="applied_yield",
        value=0,
        value_state="numeric_zero",
    )
    assert QualityFlag.ZERO_VALUE.value in assessment.quality_flags
