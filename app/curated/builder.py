from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Mapper, Session

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
from app.curated.mappers import (
    MappedProduct,
    map_bond_kr,
    map_etf_global,
    map_etf_kr,
    map_fund_public,
)
from app.data.raw_models import (
    DatasetVersion,
    DatasetVersionStatus,
    RawBondKr,
    RawEtfGlobal,
    RawEtfKr,
    RawFund,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

ProductModel = (
    type[ProductBondKr] | type[ProductEtfKr] | type[ProductEtfGlobal] | type[ProductFundPublic]
)


class CurationError(Exception):
    pass


def _get_active_dataset_version(session: Session, version: str) -> DatasetVersion:
    dataset_version = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.version == version,
            DatasetVersion.status == DatasetVersionStatus.ACTIVE.value,
        )
    )
    if dataset_version is None:
        msg = f"active dataset version not found: {version}"
        raise CurationError(msg)
    return dataset_version


def _existing_success_run(session: Session, dataset_version_id: int) -> CurationRun | None:
    return session.scalar(
        select(CurationRun).where(
            CurationRun.dataset_version_id == dataset_version_id,
            CurationRun.status == CurationRunStatus.SUCCESS.value,
        )
    )


def _clear_curated_for_version(session: Session, dataset_version_id: int) -> None:
    for model in (
        ProductQualityIssue,
        ProductMetricValue,
        ProductBondKr,
        ProductEtfKr,
        ProductEtfGlobal,
        ProductFundPublic,
        CurationRun,
    ):
        session.execute(delete(model).where(model.dataset_version_id == dataset_version_id))


def _insert_mapped_batch(
    session: Session,
    *,
    dataset_version_id: int,
    product_model: ProductModel,
    mapped_batch: list[MappedProduct],
) -> None:
    if not mapped_batch:
        return

    session.bulk_insert_mappings(
        cast(Mapper[Any], product_model), [item.product for item in mapped_batch]
    )

    metric_rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []
    for item in mapped_batch:
        product_uid = item.product["product_uid"]
        family = item.product["product_family"]
        for metric in item.metrics:
            metric_rows.append(
                {
                    "dataset_version_id": dataset_version_id,
                    "product_uid": product_uid,
                    "product_family": family,
                    "logical_field_stub": metric.logical_field_stub,
                    "source_field": metric.source_field,
                    "raw_value_text": metric.raw_value_text,
                    "normalized_value_text": metric.normalized_value_text,
                    "normalized_value_numeric": metric.normalized_value_numeric,
                    "unit": metric.unit,
                    "as_of_date": metric.as_of_date,
                    "quality_flags": metric.quality_flags,
                    "derivation": metric.derivation,
                }
            )
        for issue in item.quality_issues:
            issue_rows.append(
                {
                    "dataset_version_id": dataset_version_id,
                    "product_uid": product_uid,
                    "product_family": family,
                    "source_field": issue.source_field,
                    "quality_flag": issue.quality_flag,
                    "severity": issue.severity,
                    "message": issue.message,
                }
            )

    if metric_rows:
        session.bulk_insert_mappings(cast(Mapper[Any], ProductMetricValue), metric_rows)
    if issue_rows:
        session.bulk_insert_mappings(cast(Mapper[Any], ProductQualityIssue), issue_rows)


def _summarize_flags(session: Session, dataset_version_id: int) -> dict[str, int]:
    rows = session.scalars(
        select(ProductQualityIssue.quality_flag).where(
            ProductQualityIssue.dataset_version_id == dataset_version_id
        )
    ).all()
    return dict(Counter(rows))


def build_curated(session: Session, dataset_version_name: str) -> CurationRun:
    dataset_version = _get_active_dataset_version(session, dataset_version_name)
    existing = _existing_success_run(session, dataset_version.id)
    if existing is not None:
        logger.info("curation already complete for %s", dataset_version_name)
        return existing

    _clear_curated_for_version(session, dataset_version.id)
    session.flush()

    curation_run = CurationRun(
        dataset_version_id=dataset_version.id,
        status=CurationRunStatus.RUNNING.value,
    )
    session.add(curation_run)
    session.flush()

    row_counts: dict[str, int] = {}
    try:
        bond_batch: list[MappedProduct] = []
        for bond_row in session.scalars(
            select(RawBondKr)
            .where(RawBondKr.dataset_version_id == dataset_version.id)
            .order_by(RawBondKr.id)
        ).yield_per(BATCH_SIZE):
            bond_batch.append(map_bond_kr(bond_row))
            if len(bond_batch) >= BATCH_SIZE:
                _insert_mapped_batch(
                    session,
                    dataset_version_id=dataset_version.id,
                    product_model=ProductBondKr,
                    mapped_batch=bond_batch,
                )
                bond_batch.clear()
        if bond_batch:
            _insert_mapped_batch(
                session,
                dataset_version_id=dataset_version.id,
                product_model=ProductBondKr,
                mapped_batch=bond_batch,
            )
        row_counts["product_bond_kr"] = session.scalar(
            select(func.count())
            .select_from(ProductBondKr)
            .where(ProductBondKr.dataset_version_id == dataset_version.id)
        ) or 0

        etf_kr_batch: list[MappedProduct] = []
        for etf_kr_row in session.scalars(
            select(RawEtfKr)
            .where(RawEtfKr.dataset_version_id == dataset_version.id)
            .order_by(RawEtfKr.id)
        ).yield_per(BATCH_SIZE):
            etf_kr_batch.append(map_etf_kr(etf_kr_row))
            if len(etf_kr_batch) >= BATCH_SIZE:
                _insert_mapped_batch(
                    session,
                    dataset_version_id=dataset_version.id,
                    product_model=ProductEtfKr,
                    mapped_batch=etf_kr_batch,
                )
                etf_kr_batch.clear()
        if etf_kr_batch:
            _insert_mapped_batch(
                session,
                dataset_version_id=dataset_version.id,
                product_model=ProductEtfKr,
                mapped_batch=etf_kr_batch,
            )
        row_counts["product_etf_kr"] = session.scalar(
            select(func.count())
            .select_from(ProductEtfKr)
            .where(ProductEtfKr.dataset_version_id == dataset_version.id)
        ) or 0

        etf_global_batch: list[MappedProduct] = []
        for etf_global_row in session.scalars(
            select(RawEtfGlobal)
            .where(RawEtfGlobal.dataset_version_id == dataset_version.id)
            .order_by(RawEtfGlobal.id)
        ).yield_per(BATCH_SIZE):
            etf_global_batch.append(map_etf_global(etf_global_row))
            if len(etf_global_batch) >= BATCH_SIZE:
                _insert_mapped_batch(
                    session,
                    dataset_version_id=dataset_version.id,
                    product_model=ProductEtfGlobal,
                    mapped_batch=etf_global_batch,
                )
                etf_global_batch.clear()
        if etf_global_batch:
            _insert_mapped_batch(
                session,
                dataset_version_id=dataset_version.id,
                product_model=ProductEtfGlobal,
                mapped_batch=etf_global_batch,
            )
        row_counts["product_etf_global"] = session.scalar(
            select(func.count())
            .select_from(ProductEtfGlobal)
            .where(ProductEtfGlobal.dataset_version_id == dataset_version.id)
        ) or 0

        fund_batch: list[MappedProduct] = []
        skipped_private = 0
        for fund_row in session.scalars(
            select(RawFund)
            .where(RawFund.dataset_version_id == dataset_version.id)
            .order_by(RawFund.id)
        ).yield_per(BATCH_SIZE):
            mapped = map_fund_public(fund_row)
            if mapped is None:
                skipped_private += 1
                continue
            fund_batch.append(mapped)
            if len(fund_batch) >= BATCH_SIZE:
                _insert_mapped_batch(
                    session,
                    dataset_version_id=dataset_version.id,
                    product_model=ProductFundPublic,
                    mapped_batch=fund_batch,
                )
                fund_batch.clear()
        if fund_batch:
            _insert_mapped_batch(
                session,
                dataset_version_id=dataset_version.id,
                product_model=ProductFundPublic,
                mapped_batch=fund_batch,
            )
        row_counts["product_fund_public"] = session.scalar(
            select(func.count())
            .select_from(ProductFundPublic)
            .where(ProductFundPublic.dataset_version_id == dataset_version.id)
        ) or 0
        row_counts["fund_private_skipped"] = skipped_private

        for table, expected in EXPECTED_CURATED_COUNTS.items():
            actual = row_counts.get(table, 0)
            if actual != expected:
                msg = f"curated count mismatch for {table}: expected {expected}, got {actual}"
                raise CurationError(msg)

        curation_run.row_counts = row_counts
        curation_run.flag_summary = _summarize_flags(session, dataset_version.id)
        curation_run.status = CurationRunStatus.SUCCESS.value
        curation_run.finished_at = datetime.now(UTC)
        session.commit()
        reloaded = session.get(CurationRun, curation_run.id)
        if reloaded is None:
            msg = "curation_run missing after commit"
            raise CurationError(msg)
        logger.info("curation complete: %s", row_counts)
        return reloaded
    except Exception:
        session.rollback()
        raise
