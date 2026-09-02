from __future__ import annotations

from typing import Any, cast

from sqlalchemy.orm import InstrumentedAttribute

from app.curated.curated_models import (
    ProductBondKr,
    ProductEtfGlobal,
    ProductEtfKr,
    ProductFundPublic,
)
from app.query.enums import ProductFamily
from app.query.registry import FieldRegistry, get_field_registry

# envelope 논리 필드 → Curated envelope 컬럼
ENVELOPE_COLUMNS: dict[str, str] = {
    "product_name": "product_name_normalized",
    "manager_or_issuer": "manager_or_issuer_raw",
    "currency": "currency_raw",
    "market": "market_raw",
    "asset_type": "asset_type_raw",
    "investment_region": "investment_region_raw",
    "risk_label": "risk_label_raw",
    "sale_status": "sale_status_raw",
}

FAMILY_MODELS = {
    ProductFamily.BOND_KR: ProductBondKr,
    ProductFamily.ETF_KR: ProductEtfKr,
    ProductFamily.ETF_GLOBAL: ProductEtfGlobal,
    ProductFamily.FUND_PUBLIC: ProductFundPublic,
}

# typed 논리 필드 → Curated typed 컬럼 (registry source_field와 다를 수 있음)
TYPED_COLUMNS: dict[str, dict[ProductFamily, str]] = {
    "remaining_days": {ProductFamily.BOND_KR: "remaining_days"},
    "applied_yield": {ProductFamily.BOND_KR: "applied_yield"},
    "coupon_rate": {ProductFamily.BOND_KR: "srfc_irt"},
    "duration": {ProductFamily.BOND_KR: "dur"},
    "evaluation_price": {ProductFamily.BOND_KR: "eval_price"},
    "issue_balance": {ProductFamily.BOND_KR: "isu_bal_amt"},
    "expense_ratio": {
        ProductFamily.ETF_KR: "cu_charge_rt",
        ProductFamily.ETF_GLOBAL: "cu_charge_rt",
    },
    "base_index": {
        ProductFamily.ETF_KR: "cu_base_index",
        ProductFamily.ETF_GLOBAL: "cu_base_index",
    },
    "aum": {
        ProductFamily.ETF_KR: "du_last_aum",
        ProductFamily.ETF_GLOBAL: "du_last_aum",
        ProductFamily.FUND_PUBLIC: "fd_nast_suma",
    },
    "return_1d": {
        ProductFamily.ETF_KR: "du_er_1d",
        ProductFamily.ETF_GLOBAL: "du_er_1d",
    },
    "return_1m": {ProductFamily.FUND_PUBLIC: "fd_mm1_ern_r"},
    "return_1y": {ProductFamily.FUND_PUBLIC: "fd_yr1_ern_r"},
    "price": {ProductFamily.ETF_GLOBAL: "du_clpr"},
    "nav": {ProductFamily.ETF_GLOBAL: "du_last_nav"},
    "volume": {ProductFamily.ETF_GLOBAL: "du_vol_1d"},
    "trading_value": {ProductFamily.ETF_GLOBAL: "du_val_1d"},
}


class ColumnResolutionError(KeyError):
    pass


def get_product_model(family: ProductFamily) -> type[Any]:
    return FAMILY_MODELS[family]


def resolve_column(
    family: ProductFamily,
    logical_field: str,
    registry: FieldRegistry | None = None,
) -> InstrumentedAttribute[Any]:
    registry = registry or get_field_registry()
    model = get_product_model(family)
    if logical_field in ENVELOPE_COLUMNS:
        attr = ENVELOPE_COLUMNS[logical_field]
        return cast(InstrumentedAttribute[Any], getattr(model, attr))
    typed = TYPED_COLUMNS.get(logical_field, {})
    if family in typed:
        return cast(InstrumentedAttribute[Any], getattr(model, typed[family]))
    field_def = registry.get(logical_field)
    if field_def is None or family not in field_def.families:
        msg = f"column not resolved: {logical_field} for {family.value}"
        raise ColumnResolutionError(msg)
    source_field = field_def.families[family].source_field
    if not hasattr(model, source_field):
        msg = f"curated column missing for {logical_field}: {source_field}"
        raise ColumnResolutionError(msg)
    return cast(InstrumentedAttribute[Any], getattr(model, source_field))
