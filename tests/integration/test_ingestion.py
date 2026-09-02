from __future__ import annotations

import pytest
from app.config.settings import PROJECT_ROOT, get_settings
from app.data.ingestion import IngestionError, ingest_manifest
from app.data.raw_models import (
    DatasetVersion,
    DatasetVersionStatus,
    RawBondKr,
    RawEtfGlobal,
    RawEtfKr,
    RawFund,
)
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def test_pgvector_extension(postgres_engine: Engine, pgvector_available: None) -> None:
    with postgres_engine.connect() as connection:
        result = connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()
        assert result == "vector"


def test_full_ingestion_row_counts(db_session: Session) -> None:
    manifest_path = PROJECT_ROOT / "data/manifests/source_manifest.json"
    source_dir = get_settings().resolved_source_data_dir()
    dataset_version = ingest_manifest(db_session, manifest_path, source_dir)

    assert dataset_version.status == DatasetVersionStatus.ACTIVE.value
    assert dataset_version.actual_row_count == 53375

    counts = {
        "raw_bond_kr": db_session.scalar(select(func.count()).select_from(RawBondKr)),
        "raw_etf_kr": db_session.scalar(select(func.count()).select_from(RawEtfKr)),
        "raw_etf_global": db_session.scalar(select(func.count()).select_from(RawEtfGlobal)),
        "raw_fund": db_session.scalar(select(func.count()).select_from(RawFund)),
    }
    assert counts == {
        "raw_bond_kr": 21882,
        "raw_etf_kr": 1780,
        "raw_etf_global": 6037,
        "raw_fund": 23676,
    }


def test_reingest_is_idempotent(db_session: Session) -> None:
    manifest_path = PROJECT_ROOT / "data/manifests/source_manifest.json"
    source_dir = get_settings().resolved_source_data_dir()
    first = ingest_manifest(db_session, manifest_path, source_dir)
    second = ingest_manifest(db_session, manifest_path, source_dir)
    assert first.id == second.id

    total = db_session.scalar(select(func.count()).select_from(RawFund))
    assert total == 23676


def test_ingestion_rollback_on_failure(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = PROJECT_ROOT / "data/manifests/source_manifest.json"
    source_dir = get_settings().resolved_source_data_dir()

    def skip_validation(*_args: object, **_kwargs: object) -> None:
        return None

    def fail_ingest(*_args: object, **_kwargs: object) -> int:
        raise IngestionError("simulated mid-ingest failure")

    monkeypatch.setattr("app.data.ingestion.validate_or_raise", skip_validation)
    monkeypatch.setattr("app.data.ingestion._ingest_dataset_file", fail_ingest)

    with pytest.raises(IngestionError):
        ingest_manifest(db_session, manifest_path, source_dir)

    count = db_session.scalar(select(func.count()).select_from(DatasetVersion))
    assert count == 0
