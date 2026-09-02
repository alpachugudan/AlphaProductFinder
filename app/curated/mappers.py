from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.curated.normalize import normalize_product_name, parse_as_of_date, raw_text
from app.curated.product_family import ProductFamily
from app.curated.product_uid import build_product_uid
from app.curated.quality import (
    QualityFlag,
    assess_metric,
    merge_flags,
    severity_for_flag,
)
from app.data.raw_models import RawBondKr, RawEtfGlobal, RawEtfKr, RawFund, RawRowMixin

FUND_PUBLIC_FILTER_VALUE = "공모"

# 국내 ETF 부분 커버리지 기준선 — 데이터셋 통계
ETF_KR_PARTIAL_COVERAGE_FIELDS = frozenset({"cu_charge_rt", "cu_base_index"})


@dataclass(slots=True)
class MappedMetric:
    logical_field_stub: str
    source_field: str
    raw_value_text: str | None
    normalized_value_text: str | None
    normalized_value_numeric: float | None
    unit: str | None
    as_of_date: Any
    quality_flags: list[str]
    derivation: str = "SOURCE"


@dataclass(slots=True)
class MappedQualityIssue:
    source_field: str
    quality_flag: str
    severity: str
    message: str | None = None


@dataclass(slots=True)
class MappedProduct:
    product: dict[str, Any]
    metrics: list[MappedMetric] = field(default_factory=list)
    quality_issues: list[MappedQualityIssue] = field(default_factory=list)


def _payload_field(
    payload: dict[str, Any], value_states: dict[str, str], name: str
) -> tuple[Any, str | None]:
    return payload.get(name), value_states.get(name)


def _logical_stub(family: ProductFamily, source_field: str) -> str:
    return f"{family.value}.{source_field}"


def _metric_from_field(
    family: ProductFamily,
    payload: dict[str, Any],
    value_states: dict[str, str],
    source_field: str,
    *,
    as_of_date: Any = None,
    extra_flags: list[str] | None = None,
    unit: str | None = None,
) -> MappedMetric:
    value, state = _payload_field(payload, value_states, source_field)
    assessment = assess_metric(
        source_field=source_field,
        value=value,
        value_state=state,
        as_of_date=as_of_date,
        extra_flags=extra_flags,
    )
    return MappedMetric(
        logical_field_stub=_logical_stub(family, source_field),
        source_field=source_field,
        raw_value_text=assessment.raw_value_text,
        normalized_value_text=assessment.normalized_value_text,
        normalized_value_numeric=assessment.normalized_value_numeric,
        unit=unit,
        as_of_date=assessment.as_of_date,
        quality_flags=assessment.quality_flags,
        derivation=assessment.derivation,
    )


def _issues_from_metric(family: ProductFamily, metric: MappedMetric) -> list[MappedQualityIssue]:
    issues: list[MappedQualityIssue] = []
    for flag_name in metric.quality_flags:
        flag = QualityFlag(flag_name)
        issues.append(
            MappedQualityIssue(
                source_field=metric.source_field,
                quality_flag=flag.value,
                severity=severity_for_flag(flag).value,
                message=f"{metric.logical_field_stub}: {flag.value}",
            )
        )
    return issues


def _envelope(
    *,
    family: ProductFamily,
    raw_row: RawRowMixin,
    payload: dict[str, Any],
    product_name: Any,
    manager: Any,
    currency: Any,
    market: Any,
    asset_type: Any,
    region: Any,
    risk: Any,
    sale_status: Any,
    primary_as_of: Any,
    row_quality_flags: list[str],
) -> dict[str, Any]:
    product_uid = build_product_uid(family, payload, raw_row.source_key)
    return {
        "product_uid": product_uid,
        "dataset_version_id": raw_row.dataset_version_id,
        "source_table": raw_row.source_table,
        "source_key": raw_row.source_key,
        "raw_row_id": raw_row.id,
        "product_family": family.value,
        "product_name": raw_text(product_name),
        "product_name_normalized": normalize_product_name(product_name),
        "manager_or_issuer_raw": raw_text(manager),
        "currency_raw": raw_text(currency),
        "market_raw": raw_text(market),
        "asset_type_raw": raw_text(asset_type),
        "investment_region_raw": raw_text(region),
        "risk_label_raw": raw_text(risk),
        "sale_status_raw": raw_text(sale_status),
        "primary_as_of_date": parse_as_of_date(primary_as_of),
        "quality_flags": row_quality_flags,
    }


def map_bond_kr(raw_row: RawBondKr) -> MappedProduct:
    payload = raw_row.payload
    value_states = raw_row.value_states
    family = ProductFamily.BOND_KR

    info_base_dt = payload.get("info_base_dt")
    metrics = [
        _metric_from_field(
            family,
            payload,
            value_states,
            "remaining_days",
            as_of_date=parse_as_of_date(payload.get("sale_yield_base_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "applied_yield",
            as_of_date=parse_as_of_date(payload.get("sale_yield_base_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "dur",
            as_of_date=parse_as_of_date(payload.get("exg_close_price_base_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "eval_price",
            as_of_date=parse_as_of_date(payload.get("exg_close_price_base_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "buyable_quantity",
        ),
    ]

    row_flags = merge_flags(*(m.quality_flags for m in metrics))
    product = _envelope(
        family=family,
        raw_row=raw_row,
        payload=payload,
        product_name=payload.get("pd_nm"),
        manager=payload.get("pd_pbcm"),
        currency=payload.get("curr_cd"),
        market=payload.get("pd_exg_mkt"),
        asset_type=payload.get("bd_knd"),
        region=None,
        risk=payload.get("pd_risk_nm"),
        sale_status=None,
        primary_as_of=info_base_dt,
        row_quality_flags=row_flags,
    )
    product.update(
        {
            "pd_no": raw_text(payload.get("pd_no")),
            "pd_exg_mkt": raw_text(payload.get("pd_exg_mkt")),
            "info_base_dt": raw_text(info_base_dt),
            "info_seq": payload.get("info_seq"),
            "remaining_days": metrics[0].normalized_value_numeric,
            "applied_yield": metrics[1].normalized_value_numeric,
            "srfc_irt": assess_metric(
                source_field="srfc_irt",
                value=payload.get("srfc_irt"),
                value_state=value_states.get("srfc_irt"),
            ).normalized_value_numeric,
            "dur": metrics[2].normalized_value_numeric,
            "eval_price": metrics[3].normalized_value_numeric,
            "isu_bal_amt": assess_metric(
                source_field="isu_bal_amt",
                value=payload.get("isu_bal_amt"),
                value_state=value_states.get("isu_bal_amt"),
            ).normalized_value_numeric,
        }
    )

    issues: list[MappedQualityIssue] = []
    for metric in metrics:
        issues.extend(_issues_from_metric(family, metric))

    return MappedProduct(product=product, metrics=metrics, quality_issues=issues)


def map_etf_kr(raw_row: RawEtfKr) -> MappedProduct:
    payload = raw_row.payload
    value_states = raw_row.value_states
    family = ProductFamily.ETF_KR

    lste_dt = payload.get("pd_lste_dt")
    lste_flags: list[str] = []
    if raw_text(lste_dt) == "99991231":
        lste_flags.append(QualityFlag.SENTINEL_OR_INVALID_DATE.value)

    metrics = [
        _metric_from_field(
            family,
            payload,
            value_states,
            "du_er_1d",
            as_of_date=parse_as_of_date(payload.get("du_upt_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "du_last_aum",
            as_of_date=parse_as_of_date(payload.get("du_upt_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "cu_charge_rt",
            as_of_date=parse_as_of_date(payload.get("wu_upt_dt")),
            extra_flags=[QualityFlag.PARTIAL_COVERAGE.value]
            if value_states.get("cu_charge_rt") == "empty"
            else None,
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "cu_base_index",
            as_of_date=parse_as_of_date(payload.get("wu_upt_dt")),
            extra_flags=[QualityFlag.PARTIAL_COVERAGE.value]
            if value_states.get("cu_base_index") == "empty"
            else None,
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "pd_lste_dt",
            extra_flags=lste_flags or None,
        ),
    ]

    sale_status = "|".join(
        filter(
            None,
            [
                raw_text(payload.get("pd_sale_yn")),
                raw_text(payload.get("pd_tr_yn")),
                raw_text(payload.get("pd_pen_tr_yn")),
            ],
        )
    )
    row_flags = merge_flags(*(m.quality_flags for m in metrics))
    product = _envelope(
        family=family,
        raw_row=raw_row,
        payload=payload,
        product_name=payload.get("pd_nm"),
        manager=payload.get("cu_fund_mgmt_co"),
        currency=None,
        market=None,
        asset_type=payload.get("wu_inv_ast_type"),
        region=payload.get("wu_inv_rgn"),
        risk=None,
        sale_status=sale_status or None,
        primary_as_of=payload.get("du_upt_dt"),
        row_quality_flags=row_flags,
    )
    product.update(
        {
            "pd_itm_no": raw_text(payload.get("pd_itm_no")),
            "pd_ticker": raw_text(payload.get("pd_ticker")),
            "pd_lste_dt": raw_text(lste_dt),
            "du_er_1d": metrics[0].normalized_value_numeric,
            "du_last_aum": metrics[1].normalized_value_numeric,
            "cu_charge_rt": metrics[2].normalized_value_numeric,
            "cu_base_index": metrics[3].raw_value_text,
        }
    )

    issues: list[MappedQualityIssue] = []
    for metric in metrics:
        issues.extend(_issues_from_metric(family, metric))

    return MappedProduct(product=product, metrics=metrics, quality_issues=issues)


def map_etf_global(raw_row: RawEtfGlobal) -> MappedProduct:
    payload = raw_row.payload
    value_states = raw_row.value_states
    family = ProductFamily.ETF_GLOBAL

    date_mismatch_flags: list[str] = []
    match_yn = raw_text(payload.get("du_base_dt_match_yn"))
    if match_yn == "N":
        date_mismatch_flags.append(QualityFlag.DATE_MISMATCH.value)

    clpr_base = parse_as_of_date(payload.get("du_clpr_base_dt"))
    nav_base = parse_as_of_date(payload.get("du_nav_base_dt"))

    metrics = [
        _metric_from_field(
            family,
            payload,
            value_states,
            "du_clpr",
            as_of_date=clpr_base,
            extra_flags=date_mismatch_flags or None,
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "du_last_nav",
            as_of_date=nav_base,
            extra_flags=date_mismatch_flags or None,
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "du_last_aum",
            as_of_date=parse_as_of_date(payload.get("du_upt_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "du_er_1d",
            as_of_date=parse_as_of_date(payload.get("du_upt_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "du_diff_rt",
            extra_flags=date_mismatch_flags or None,
        ),
    ]

    row_flags = merge_flags(*(m.quality_flags for m in metrics))
    product = _envelope(
        family=family,
        raw_row=raw_row,
        payload=payload,
        product_name=payload.get("pd_nm"),
        manager=payload.get("cu_fund_mgmt_co"),
        currency=None,
        market=None,
        asset_type=payload.get("wu_inv_ast_type"),
        region=payload.get("wu_inv_rgn"),
        risk=None,
        sale_status=raw_text(payload.get("pd_sale_yn")),
        primary_as_of=payload.get("du_upt_dt"),
        row_quality_flags=row_flags,
    )
    product.update(
        {
            "pd_itm_no": raw_text(payload.get("pd_itm_no")),
            "du_clpr": metrics[0].normalized_value_numeric,
            "du_last_nav": metrics[1].normalized_value_numeric,
            "du_last_aum": metrics[2].normalized_value_numeric,
            "du_er_1d": metrics[3].normalized_value_numeric,
            "du_val_1d": assess_metric(
                source_field="du_val_1d",
                value=payload.get("du_val_1d"),
                value_state=value_states.get("du_val_1d"),
            ).normalized_value_numeric,
            "du_vol_1d": assess_metric(
                source_field="du_vol_1d",
                value=payload.get("du_vol_1d"),
                value_state=value_states.get("du_vol_1d"),
            ).normalized_value_numeric,
            "du_clpr_base_dt": clpr_base,
            "du_nav_base_dt": nav_base,
            "du_base_dt_match_yn": match_yn,
        }
    )

    issues: list[MappedQualityIssue] = []
    for metric in metrics:
        issues.extend(_issues_from_metric(family, metric))

    return MappedProduct(product=product, metrics=metrics, quality_issues=issues)


def should_include_fund_public(payload: dict[str, Any]) -> bool:
    return raw_text(payload.get("prvo_pbff_desc")) == FUND_PUBLIC_FILTER_VALUE


def map_fund_public(raw_row: RawFund) -> MappedProduct | None:
    payload = raw_row.payload
    if not should_include_fund_public(payload):
        return None

    value_states = raw_row.value_states
    family = ProductFamily.FUND_PUBLIC

    metrics = [
        _metric_from_field(
            family,
            payload,
            value_states,
            "fd_wk1_ern_r",
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "fd_mm1_ern_r",
            as_of_date=parse_as_of_date(payload.get("fd_price_bas_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "fd_yr1_ern_r",
            as_of_date=parse_as_of_date(payload.get("fd_price_bas_dt")),
        ),
        _metric_from_field(
            family,
            payload,
            value_states,
            "fd_nast_suma",
            as_of_date=parse_as_of_date(payload.get("fd_price_bas_dt")),
        ),
    ]

    sale_status = "|".join(
        filter(
            None,
            [raw_text(payload.get("sale_yn")), raw_text(payload.get("thco_sale_yn"))],
        )
    )
    row_flags = merge_flags(*(m.quality_flags for m in metrics))
    product = _envelope(
        family=family,
        raw_row=raw_row,
        payload=payload,
        product_name=payload.get("itm_nm"),
        manager=None,
        currency=None,
        market=None,
        asset_type=payload.get("or_attr_desc"),
        region=payload.get("fd_ivst_rgn_desc"),
        risk=payload.get("zrin_fd_ivst_risk_grd_nm"),
        sale_status=sale_status or None,
        primary_as_of=payload.get("fd_price_bas_dt"),
        row_quality_flags=row_flags,
    )
    price_bas_dt = parse_as_of_date(payload.get("fd_price_bas_dt"))
    product.update(
        {
            "itm_no": raw_text(payload.get("itm_no")),
            "itm_abrv_nm": raw_text(payload.get("itm_abrv_nm")),
            "fd_mm1_ern_r": metrics[1].normalized_value_numeric,
            "fd_yr1_ern_r": metrics[2].normalized_value_numeric,
            "fd_nast_suma": metrics[3].normalized_value_numeric,
            "fd_price_bas_dt": price_bas_dt,
        }
    )

    issues: list[MappedQualityIssue] = []
    for metric in metrics:
        issues.extend(_issues_from_metric(family, metric))

    return MappedProduct(product=product, metrics=metrics, quality_issues=issues)
