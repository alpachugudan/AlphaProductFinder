from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from app.config.settings import PROJECT_ROOT, get_settings
from app.curated.builder import build_curated
from app.data.ingestion import ingest_manifest
from app.db.session import get_engine
from app.external.ingestion import compute_manifest_hash, ingest_external
from app.query.enums import EntityType, Intent, ProductFamily, RelationType
from app.query.models import EntityClause, QuerySpec, RelationshipFilterClause
from app.retrieval.document_retriever import DocumentRetriever
from app.retrieval.models import RetrievalContext
from app.retrieval.relation_retriever import RelationRetriever
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(scope="module")
def external_session(postgres_engine: Engine) -> Generator[Session, None, None]:
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
    ingest_external(session)
    yield session
    session.close()


@pytest.fixture(scope="module")
def dataset_version_id(external_session: Session) -> int:
    from app.data.raw_models import DatasetVersion, DatasetVersionStatus

    version_id = external_session.scalar(
        select(DatasetVersion.id).where(DatasetVersion.status == DatasetVersionStatus.ACTIVE.value)
    )
    assert version_id is not None
    return int(version_id)


def test_external_ingest_is_idempotent(external_session: Session) -> None:
    first = ingest_external(external_session)
    second = ingest_external(external_session)
    assert first.manifest_hash == second.manifest_hash
    assert first.id == second.id


def test_holdings_relation_search(external_session: Session, dataset_version_id: int) -> None:
    spec = QuerySpec(
        intent=Intent.RELATION_SEARCH,
        product_families=[ProductFamily.ETF_KR],
        relationship_filters=[
            RelationshipFilterClause(relation=RelationType.HOLDS, target_entity="삼성전자")
        ],
        limit=5,
    )
    context = RetrievalContext(
        dataset_version_id=dataset_version_id,
        dataset_version_label="2026-07-11-baseline",
        session=external_session,
    )
    result = RelationRetriever().retrieve_sync(spec, context)
    assert result.relation_evidences
    assert all(item.source_document_id for item in result.relation_evidences)
    assert all(item.content_sha256 for item in result.relation_evidences)


def test_document_hybrid_search_is_deterministic(
    external_session: Session, dataset_version_id: int
) -> None:
    spec = QuerySpec(
        intent=Intent.EXPLAIN_TERM,
        product_families=[ProductFamily.ETF_KR],
        entities=[EntityClause(text="삼성전자", entity_type=EntityType.COMPANY)],
        limit=3,
    )
    context = RetrievalContext(
        dataset_version_id=dataset_version_id,
        dataset_version_label="2026-07-11-baseline",
        session=external_session,
    )
    retriever = DocumentRetriever()
    first = retriever.retrieve_sync(spec, context)
    second = retriever.retrieve_sync(spec, context)
    assert [item.chunk_id for item in first.document_evidences] == [
        item.chunk_id for item in second.document_evidences
    ]


def test_evaluation_path_has_zero_network_calls(
    external_session: Session, dataset_version_id: int
) -> None:
    spec = QuerySpec(
        intent=Intent.RELATION_SEARCH,
        product_families=[ProductFamily.ETF_KR],
        relationship_filters=[
            RelationshipFilterClause(relation=RelationType.HOLDS, target_entity="삼성전자")
        ],
    )
    context = RetrievalContext(
        dataset_version_id=dataset_version_id,
        dataset_version_label="2026-07-11-baseline",
        session=external_session,
    )

    with patch("urllib.request.urlopen") as urlopen_mock:
        RelationRetriever().retrieve_sync(spec, context)
        DocumentRetriever().retrieve_sync(
            QuerySpec(
                intent=Intent.EXPLAIN_TERM,
                product_families=[ProductFamily.ETF_KR],
                entities=[EntityClause(text="반도체", entity_type=EntityType.THEME)],
            ),
            context,
        )
        urlopen_mock.assert_not_called()


def test_manifest_hash_changes_when_manifest_changes(tmp_path) -> None:
    manifest = tmp_path / "external_manifest.yaml"
    manifest.write_text("snapshot_version: test-a\n", encoding="utf-8")
    hash_a = compute_manifest_hash(manifest)
    manifest.write_text("snapshot_version: test-b\n", encoding="utf-8")
    hash_b = compute_manifest_hash(manifest)
    assert hash_a != hash_b


def test_exact_alias_resolution_from_fixture(external_session: Session) -> None:
    from app.external.resolution import resolve_entity_exact

    result = resolve_entity_exact(external_session, "삼성전자")
    assert result.entity_ids
    assert result.match_method == "ALIAS_EXACT"


def test_fuzzy_only_alias_not_auto_approved(external_session: Session) -> None:
    from datetime import UTC, datetime

    from app.external.models import Entity, EntityAlias, SourceDocument
    from app.external.resolution import resolve_entity_exact

    external_session.add(
        SourceDocument(
            document_id="doc-fuzzy-test",
            source_type="OFFICIAL_IR",
            title="t",
            publisher="p",
            collected_at=datetime.now(UTC),
            local_path="x",
            content_sha256="feedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedface",
            parser_version="1.0.0",
        )
    )
    external_session.flush()
    external_session.add(
        Entity(
            entity_id="ENT:TEST:FUZZY",
            entity_type="COMPANY",
            canonical_name="Fuzzy Only Corp",
        )
    )
    external_session.add(
        EntityAlias(
            alias="FuzzyOnly",
            normalized_alias="fuzzyonly",
            entity_id="ENT:TEST:FUZZY",
            alias_type="KO_NAME",
            source_document_id="doc-fuzzy-test",
            match_method="FUZZY",
            review_status="APPROVED",
        )
    )
    external_session.commit()

    result = resolve_entity_exact(external_session, "FuzzyOnly")
    assert result.unresolved is True
