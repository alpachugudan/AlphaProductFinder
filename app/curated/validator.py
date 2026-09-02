from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.curated.curated_models import (
    EXPECTED_CURATED_COUNTS,
    CurationRun,
    CurationRunStatus,
    ProductBondKr,
    ProductEtfGlobal,
    ProductEtfKr,
    ProductFundPublic,
    ProductMetricValue,
    ProductQualityIssue,
)
from app.curated.quality import QualityFlag
from app.data.raw_models import DatasetVersion, DatasetVersionStatus, RawFund


class CuratedValidationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CuratedValidationReport:
    dataset_version: str
    row_counts: dict[str, int]
    flag_summary: dict[str, int]
    fund_private_skipped: int


def validate_curated(session: Session, dataset_version_name: str) -> CuratedValidationReport:
    dataset_version = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.version == dataset_version_name,
            DatasetVersion.status == DatasetVersionStatus.ACTIVE.value,
        )
    )
    if dataset_version is None:
        msg = f"active dataset version not found: {dataset_version_name}"
        raise CuratedValidationError(msg)

    curation_run = session.scalar(
        select(CurationRun).where(
            CurationRun.dataset_version_id == dataset_version.id,
            CurationRun.status == CurationRunStatus.SUCCESS.value,
        )
    )
    if curation_run is None:
        msg = f"successful curation_run not found for {dataset_version_name}"
        raise CuratedValidationError(msg)

    counts = {
        "product_bond_kr": session.scalar(
            select(func.count())
            .select_from(ProductBondKr)
            .where(ProductBondKr.dataset_version_id == dataset_version.id)
        )
        or 0,
        "product_etf_kr": session.scalar(
            select(func.count())
            .select_from(ProductEtfKr)
            .where(ProductEtfKr.dataset_version_id == dataset_version.id)
        )
        or 0,
        "product_etf_global": session.scalar(
            select(func.count())
            .select_from(ProductEtfGlobal)
            .where(ProductEtfGlobal.dataset_version_id == dataset_version.id)
        )
        or 0,
        "product_fund_public": session.scalar(
            select(func.count())
            .select_from(ProductFundPublic)
            .where(ProductFundPublic.dataset_version_id == dataset_version.id)
        )
        or 0,
    }

    for table, expected in EXPECTED_CURATED_COUNTS.items():
        actual = counts[table]
        if actual != expected:
            msg = f"curated count mismatch for {table}: expected {expected}, got {actual}"
            raise CuratedValidationError(msg)

    fund_private_skipped = (session.scalar(select(func.count()).select_from(RawFund).where(
        RawFund.dataset_version_id == dataset_version.id
    )) or 0) - counts["product_fund_public"]
    if fund_private_skipped != 8960:
        msg = f"expected 8960 private fund rows skipped, got {fund_private_skipped}"
        raise CuratedValidationError(msg)

    buyable_metrics = session.scalars(
        select(ProductMetricValue).where(
            ProductMetricValue.dataset_version_id == dataset_version.id,
            ProductMetricValue.source_field == "buyable_quantity",
        )
    ).all()
    for metric in buyable_metrics:
        if QualityFlag.INVALID_FOR_DECISION.value not in metric.quality_flags:
            msg = "buyable_quantity missing INVALID_FOR_DECISION flag"
            raise CuratedValidationError(msg)

    wk1_blocked = session.scalar(
        select(func.count())
        .select_from(ProductMetricValue)
        .where(
            ProductMetricValue.dataset_version_id == dataset_version.id,
            ProductMetricValue.source_field == "fd_wk1_ern_r",
            ProductMetricValue.quality_flags.contains(
                [QualityFlag.FEATURE_NOT_AVAILABLE_FOR_MARKET.value]
            ),
        )
    )
    if wk1_blocked != counts["product_fund_public"]:
        msg = "fd_wk1_ern_r must be blocked for all public funds"
        raise CuratedValidationError(msg)

    view_count = session.execute(
        text("SELECT COUNT(*) FROM product_search_view WHERE dataset_version_id = :version_id"),
        {"version_id": dataset_version.id},
    ).scalar_one()
    expected_view = sum(counts.values())
    if view_count != expected_view:
        msg = f"product_search_view count mismatch: expected {expected_view}, got {view_count}"
        raise CuratedValidationError(msg)

    flag_rows = session.scalars(
        select(ProductQualityIssue.quality_flag).where(
            ProductQualityIssue.dataset_version_id == dataset_version.id
        )
    ).all()
    flag_summary: dict[str, int] = {}
    for flag in flag_rows:
        flag_summary[flag] = flag_summary.get(flag, 0) + 1

    skipped = (curation_run.row_counts or {}).get("fund_private_skipped", 0)
    return CuratedValidationReport(
        dataset_version=dataset_version_name,
        row_counts=counts,
        flag_summary=flag_summary,
        fund_private_skipped=int(skipped),
    )
