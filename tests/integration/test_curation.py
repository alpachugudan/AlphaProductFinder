from __future__ import annotations

from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from app.config.settings import PROJECT_ROOT, get_settings
from app.curated.builder import CurationError, build_curated
from app.curated.curated_models import EXPECTED_CURATED_COUNTS, ProductBondKr, ProductFundPublic
from app.curated.validator import validate_curated
from app.data.ingestion import ingest_manifest
from app.data.raw_models import RawFund
from app.db.session import get_engine
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(scope="module")
def curated_session(postgres_engine: Engine) -> Generator[Session, None, None]:
    get_engine.cache_clear()
    get_settings.cache_clear()

    autocommit = postgres_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    autocommit.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    autocommit.execute(text("CREATE SCHEMA public"))
    autocommit.execute(text("GRANT ALL ON SCHEMA public TO public"))
    autocommit.close()

    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(alembic_config, "head")

    session = sessionmaker(bind=postgres_engine, autoflush=False, autocommit=False)()
    manifest_path = PROJECT_ROOT / "data/manifests/source_manifest.json"
    source_dir = get_settings().resolved_source_data_dir()
    ingest_manifest(session, manifest_path, source_dir)
    yield session
    session.close()


def test_build_curated_counts(curated_session: Session) -> None:
    curation_run = build_curated(curated_session, "2026-07-11-baseline")
    assert curation_run.status == "SUCCESS"
    assert curation_run.row_counts == {
        **EXPECTED_CURATED_COUNTS,
        "fund_private_skipped": 8960,
    }


def test_rebuild_curated_is_idempotent(curated_session: Session) -> None:
    first = build_curated(curated_session, "2026-07-11-baseline")
    second = build_curated(curated_session, "2026-07-11-baseline")
    assert first.id == second.id


def test_validate_curated_invariants(curated_session: Session) -> None:
    report = validate_curated(curated_session, "2026-07-11-baseline")
    assert report.row_counts == EXPECTED_CURATED_COUNTS
    assert report.fund_private_skipped == 8960


def test_private_funds_not_in_curated(curated_session: Session) -> None:
    dataset_version_id = curated_session.scalar(
        select(ProductFundPublic.dataset_version_id).limit(1)
    )
    raw_count = curated_session.scalar(
        select(func.count())
        .select_from(RawFund)
        .where(RawFund.dataset_version_id == dataset_version_id)
    )
    public_count = curated_session.scalar(
        select(func.count())
        .select_from(ProductFundPublic)
        .where(ProductFundPublic.dataset_version_id == dataset_version_id)
    )
    assert raw_count == 23676
    assert public_count == 14716
    assert raw_count - public_count == 8960


def test_bond_uid_unique_per_version(curated_session: Session) -> None:
    dataset_version_id = curated_session.scalar(select(ProductBondKr.dataset_version_id).limit(1))
    total = curated_session.scalar(
        select(func.count())
        .select_from(ProductBondKr)
        .where(ProductBondKr.dataset_version_id == dataset_version_id)
    )
    distinct = curated_session.scalar(
        select(func.count(func.distinct(ProductBondKr.product_uid))).where(
            ProductBondKr.dataset_version_id == dataset_version_id
        )
    )
    assert total == distinct == 21882


def test_curation_rollback_on_failure(
    curated_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.curated import builder

    curated_session.execute(text("DELETE FROM curation_run"))
    curated_session.execute(text("DELETE FROM product_quality_issue"))
    curated_session.execute(text("DELETE FROM product_metric_value"))
    curated_session.execute(text("DELETE FROM product_bond_kr"))
    curated_session.commit()

    def fail_map(*_args: object, **_kwargs: object):
        raise CurationError("simulated mapper failure")

    monkeypatch.setattr(builder, "map_bond_kr", fail_map)

    with pytest.raises(CurationError):
        build_curated(curated_session, "2026-07-11-baseline")

    remaining = curated_session.scalar(select(func.count()).select_from(ProductBondKr)) or 0
    assert remaining == 0

    monkeypatch.undo()
    build_curated(curated_session, "2026-07-11-baseline")
