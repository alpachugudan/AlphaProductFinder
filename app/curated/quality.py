from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.curated.normalize import parse_as_of_date, raw_text


class QualityFlag(StrEnum):
    MISSING = "MISSING"
    ZERO_VALUE = "ZERO_VALUE"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    SENTINEL_OR_INVALID_DATE = "SENTINEL_OR_INVALID_DATE"
    STALE_PRICE = "STALE_PRICE"
    MISSING_PRICE = "MISSING_PRICE"
    DATE_MISMATCH = "DATE_MISMATCH"
    JOIN_CONTAMINATION = "JOIN_CONTAMINATION"
    UNIT_OUTLIER = "UNIT_OUTLIER"
    INACTIVE_PRODUCT = "INACTIVE_PRODUCT"
    FEATURE_NOT_AVAILABLE_FOR_MARKET = "FEATURE_NOT_AVAILABLE_FOR_MARKET"
    INVALID_FOR_DECISION = "INVALID_FOR_DECISION"
    OUTLIER_REVIEW = "OUTLIER_REVIEW"


class QualitySeverity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    EXCLUDE_METRIC = "EXCLUDE_METRIC"
    BLOCK_ANSWER = "BLOCK_ANSWER"


FLAG_SEVERITY: dict[QualityFlag, QualitySeverity] = {
    QualityFlag.MISSING: QualitySeverity.WARN,
    QualityFlag.ZERO_VALUE: QualitySeverity.WARN,
    QualityFlag.PARTIAL_COVERAGE: QualitySeverity.INFO,
    QualityFlag.SENTINEL_OR_INVALID_DATE: QualitySeverity.EXCLUDE_METRIC,
    QualityFlag.STALE_PRICE: QualitySeverity.EXCLUDE_METRIC,
    QualityFlag.MISSING_PRICE: QualitySeverity.EXCLUDE_METRIC,
    QualityFlag.DATE_MISMATCH: QualitySeverity.EXCLUDE_METRIC,
    QualityFlag.JOIN_CONTAMINATION: QualitySeverity.BLOCK_ANSWER,
    QualityFlag.UNIT_OUTLIER: QualitySeverity.EXCLUDE_METRIC,
    QualityFlag.INACTIVE_PRODUCT: QualitySeverity.WARN,
    QualityFlag.FEATURE_NOT_AVAILABLE_FOR_MARKET: QualitySeverity.EXCLUDE_METRIC,
    QualityFlag.INVALID_FOR_DECISION: QualitySeverity.EXCLUDE_METRIC,
    QualityFlag.OUTLIER_REVIEW: QualitySeverity.EXCLUDE_METRIC,
}

# 대회 Q&A 기준 — 매수가능 판단에 쓰지 않는 필드
INVALID_FOR_DECISION_FIELDS = frozenset({"buyable_quantity"})

# 시장 전체 결측으로 랭킹 불가
FEATURE_UNAVAILABLE_FIELDS = frozenset({"fd_wk1_ern_r"})

SENTINEL_DATE_VALUES = frozenset({"99991231"})


@dataclass(frozen=True, slots=True)
class MetricAssessment:
    raw_value_text: str | None
    normalized_value_text: str | None
    normalized_value_numeric: float | None
    as_of_date: Any
    quality_flags: list[str]
    derivation: str = "SOURCE"


def severity_for_flag(flag: QualityFlag) -> QualitySeverity:
    return FLAG_SEVERITY[flag]


def merge_flags(*flag_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in flag_groups:
        for flag in group:
            if flag not in seen:
                seen.add(flag)
                merged.append(flag)
    return merged


def _to_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def assess_metric(
    *,
    source_field: str,
    value: Any,
    value_state: str | None,
    as_of_date: Any = None,
    extra_flags: list[str] | None = None,
) -> MetricAssessment:
    """필드 단위 품질 평가 — 원문 값은 수정하지 않음"""
    flags: list[str] = list(extra_flags or [])
    raw = raw_text(value)

    if source_field in INVALID_FOR_DECISION_FIELDS:
        flags.append(QualityFlag.INVALID_FOR_DECISION.value)
    if source_field in FEATURE_UNAVAILABLE_FIELDS:
        flags.append(QualityFlag.FEATURE_NOT_AVAILABLE_FOR_MARKET.value)

    if value is None or value_state == "empty":
        flags.append(QualityFlag.MISSING.value)
    elif value_state in {"numeric_zero", "string_zero"}:
        flags.append(QualityFlag.ZERO_VALUE.value)

    parsed_date = parse_as_of_date(value) if source_field.endswith("_dt") else None
    if raw in SENTINEL_DATE_VALUES:
        flags.append(QualityFlag.SENTINEL_OR_INVALID_DATE.value)

    numeric = _to_numeric(value)
    if source_field == "applied_yield" and numeric is not None and abs(numeric) > 100:
        flags.append(QualityFlag.OUTLIER_REVIEW.value)

    return MetricAssessment(
        raw_value_text=raw,
        normalized_value_text=raw,
        normalized_value_numeric=numeric,
        as_of_date=as_of_date or parsed_date,
        quality_flags=merge_flags(flags),
    )
