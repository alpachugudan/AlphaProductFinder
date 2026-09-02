from __future__ import annotations

import hashlib
import json
from typing import Any

from app.curated.product_family import ProductFamily


def _bond_canonical_hash(payload: dict[str, Any]) -> str:
    key_fields = ["pd_no", "pd_exg_mkt", "info_base_dt", "info_seq"]
    canonical = {field: payload[field] for field in key_fields}
    encoded = json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def build_product_uid(family: ProductFamily, payload: dict[str, Any], source_key: str) -> str:
    """데이터 버전과 무관한 안정 product_uid 생성"""
    if family == ProductFamily.BOND_KR:
        return f"BOND_KR:{_bond_canonical_hash(payload)}"
    if family == ProductFamily.ETF_KR:
        return f"ETF_KR:{payload['pd_itm_no']}"
    if family == ProductFamily.ETF_GLOBAL:
        return f"ETF_GLOBAL:{payload['pd_itm_no']}"
    if family == ProductFamily.FUND_PUBLIC:
        return f"FUND_PUBLIC:{payload['itm_no']}"
    msg = f"unsupported product family: {family}"
    raise ValueError(msg)
