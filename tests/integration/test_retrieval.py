from __future__ import annotations

from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from app.config.settings import PROJECT_ROOT, get_settings
from app.curated.builder import build_curated
from app.data.ingestion import ingest_manifest
from app.db.session import get_engine
from app.query.enums import Intent, Operator, ProductFamily
from app.query.models import QuerySpec
from app.retrieval.models import RetrievalContext
from app.retrieval.sql_retriever import SqlRetriever
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(scope="module")
def retrieval_session(postgres_engine: Engine) -> Generator[Session, None, None]:
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
    build_curated(session, "2026-07-11-baseline")
    yield session
    session.close()


@pytest.fixture(scope="module")
def dataset_version_id(retrieval_session: Session) -> int:
    from app.data.raw_models import DatasetVersion, DatasetVersionStatus

    version_id = retrieval_session.scalar(
        select(DatasetVersion.id).where(DatasetVersion.status == DatasetVersionStatus.ACTIVE.value)
    )
    assert version_id is not None
    return int(version_id)


def test_bond_filter_remaining_days(
    retrieval_session: Session, dataset_version_id: int
) -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.BOND_KR],
        filters=[{"field": "remaining_days", "operator": Operator.LTE, "value": 365}],
        limit=5,
    )
    context = RetrievalContext(
        dataset_version_id=dataset_version_id,
        dataset_version_label="2026-07-11-baseline",
        session=retrieval_session,
    )
    result = SqlRetriever().retrieve_sync(spec, context)
    assert result.count_final <= 5
    assert all(item.product_family == ProductFamily.BOND_KR for item in result.candidates)


def test_etf_kr_expense_ratio_rank_is_deterministic(
    retrieval_session: Session, dataset_version_id: int
) -> None:
    spec = QuerySpec(
        intent=Intent.FILTER_AND_RANK,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "investment_region", "operator": Operator.CONTAINS, "value": "미국"}],
        preferences=[{"field": "expense_ratio", "direction": "ASC", "priority": 1}],
        metrics=["expense_ratio"],
        limit=5,
    )
    context = RetrievalContext(
        dataset_version_id=dataset_version_id,
        dataset_version_label="2026-07-11-baseline",
        session=retrieval_session,
    )
    retriever = SqlRetriever()
    first = retriever.retrieve_sync(spec, context)
    second = retriever.retrieve_sync(spec, context)
    assert [item.product_uid for item in first.candidates] == [
        item.product_uid for item in second.candidates
    ]


def test_fund_public_only_no_private_funds(
    retrieval_session: Session, dataset_version_id: int
) -> None:
    from app.curated.curated_models import ProductFundPublic

    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.FUND_PUBLIC],
        filters=[{"field": "sale_status", "operator": Operator.EQ, "value": "Y"}],
        limit=10,
    )
    context = RetrievalContext(
        dataset_version_id=dataset_version_id,
        dataset_version_label="2026-07-11-baseline",
        session=retrieval_session,
    )
    result = SqlRetriever().retrieve_sync(spec, context)
    total_public = retrieval_session.scalar(
        select(func.count())
        .select_from(ProductFundPublic)
        .where(ProductFundPublic.dataset_version_id == dataset_version_id)
    )
    assert total_public == 14716
    assert all(item.product_family == ProductFamily.FUND_PUBLIC for item in result.candidates)
