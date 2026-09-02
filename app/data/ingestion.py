from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.excel_reader import iter_data_rows, read_data_headers
from app.data.manifest import DatasetEntry, SourceManifest, compute_manifest_hash, load_manifest
from app.data.raw_models import (
    RAW_TABLE_MODELS,
    DatasetVersion,
    DatasetVersionStatus,
    IngestionRun,
    IngestionRunStatus,
    RawRowMixin,
)
from app.data.source_key import build_source_key
from app.data.validator import validate_or_raise

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


class IngestionError(Exception):
    pass


class PayloadConflictError(IngestionError):
    pass


def _payload_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ingest_manifest(
    session: Session,
    manifest_path: Path,
    source_dir: Path,
    *,
    verify_hashes: bool = True,
) -> DatasetVersion:
    manifest = load_manifest(manifest_path)
    manifest_hash = compute_manifest_hash(manifest)

    existing = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.version == manifest.dataset_version,
            DatasetVersion.manifest_hash == manifest_hash,
            DatasetVersion.status == DatasetVersionStatus.ACTIVE.value,
        )
    )
    if existing is not None:
        logger.info("dataset version already active: %s", manifest.dataset_version)
        return existing

    validate_or_raise(manifest_path, source_dir, verify_hashes=verify_hashes)

    stale = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.version == manifest.dataset_version,
            DatasetVersion.status != DatasetVersionStatus.ACTIVE.value,
        )
    )
    if stale is not None:
        session.delete(stale)
        session.flush()

    dataset_version = DatasetVersion(
        version=manifest.dataset_version,
        manifest_hash=manifest_hash,
        expected_row_count=manifest.expected_total_rows,
        actual_row_count=None,
        status=DatasetVersionStatus.LOADING.value,
    )
    session.add(dataset_version)
    session.flush()

    ingestion_run = IngestionRun(
        dataset_version_id=dataset_version.id,
        status=IngestionRunStatus.RUNNING.value,
    )
    session.add(ingestion_run)
    session.flush()

    row_counts: dict[str, int] = {}

    try:
        for entry in manifest.datasets:
            count = _ingest_dataset_file(
                session=session,
                manifest=manifest,
                entry=entry,
                source_dir=source_dir,
                dataset_version_id=dataset_version.id,
            )
            row_counts[entry.raw_table] = count
            logger.info("ingested %s rows into %s", count, entry.raw_table)

        actual_total = sum(row_counts.values())
        if actual_total != manifest.expected_total_rows:
            msg = (
                "post-ingest row total mismatch: "
                f"expected {manifest.expected_total_rows}, got {actual_total}"
            )
            raise IngestionError(msg)

        dataset_version.actual_row_count = actual_total
        dataset_version.status = DatasetVersionStatus.VALIDATED.value
        ingestion_run.row_counts = row_counts
        ingestion_run.status = IngestionRunStatus.SUCCESS.value
        ingestion_run.finished_at = datetime.now(UTC)

        session.execute(
            update(DatasetVersion)
            .where(
                DatasetVersion.status == DatasetVersionStatus.ACTIVE.value,
                DatasetVersion.id != dataset_version.id,
            )
            .values(status=DatasetVersionStatus.VALIDATED.value)
        )
        dataset_version.status = DatasetVersionStatus.ACTIVE.value
        dataset_version.activated_at = datetime.now(UTC)
        session.commit()
        committed_id = dataset_version.id
        reloaded = session.get(DatasetVersion, committed_id)
        if reloaded is None:
            msg = f"dataset_version {committed_id} missing after commit"
            raise IngestionError(msg)
        return reloaded
    except Exception:
        session.rollback()
        raise


def _ingest_dataset_file(
    *,
    session: Session,
    manifest: SourceManifest,
    entry: DatasetEntry,
    source_dir: Path,
    dataset_version_id: int,
) -> int:
    model = RAW_TABLE_MODELS[entry.raw_table]
    data_path = source_dir / entry.data_file
    headers = read_data_headers(data_path, entry.data_sheet)
    batch: list[dict[str, Any]] = []
    inserted = 0
    existing_keys: dict[str, str] = {}

    for parsed in iter_data_rows(data_path, entry, headers):
        source_key = build_source_key(entry.source_key_fields, parsed.payload)
        fingerprint = _payload_fingerprint(parsed.payload)
        if source_key in existing_keys and existing_keys[source_key] != fingerprint:
            msg = (
                f"payload conflict for source key {source_key} in {entry.data_file} "
                f"at row {parsed.row_number}"
            )
            raise PayloadConflictError(msg)
        existing_keys[source_key] = fingerprint

        batch.append(
            {
                "dataset_version_id": dataset_version_id,
                "source_table": entry.logical_table,
                "source_key": source_key,
                "source_file": entry.data_file,
                "source_sheet": entry.data_sheet,
                "source_row_number": parsed.row_number,
                "file_sha256": entry.data_sha256,
                "payload": parsed.payload,
                "value_states": parsed.value_states,
            }
        )
        if len(batch) >= BATCH_SIZE:
            inserted += _flush_batch(session, model, batch)
            batch.clear()

    if batch:
        inserted += _flush_batch(session, model, batch)

    db_count = session.scalar(
        select(func.count())
        .select_from(model)
        .where(model.dataset_version_id == dataset_version_id)
    )
    if db_count != entry.expected_rows:
        msg = (
            f"db count mismatch for {entry.raw_table}: "
            f"expected {entry.expected_rows}, got {db_count}"
        )
        raise IngestionError(msg)
    return int(db_count or 0)


def _flush_batch(session: Session, model: type[RawRowMixin], rows: list[dict[str, Any]]) -> int:
    stmt = insert(model).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["dataset_version_id", "source_key"])
    result = session.execute(stmt)
    session.flush()
    return result.rowcount or 0
