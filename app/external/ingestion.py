from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config.settings import PROJECT_ROOT
from app.embedding.deterministic import DeterministicEmbeddingProvider
from app.external.models import (
    DocumentChunk,
    Entity,
    EntityAlias,
    EntityRelation,
    ExternalIngestionRun,
    ExternalIngestionStatus,
    ProductHolding,
    SourceDocument,
)

EXTERNAL_ROOT = PROJECT_ROOT / "data" / "external"
MANIFEST_PATH = EXTERNAL_ROOT / "manifests" / "external_manifest.yaml"
NORMALIZED_DIR = EXTERNAL_ROOT / "normalized"


class ExternalIngestionError(Exception):
    pass


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(str(value))


def _parse_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def compute_manifest_hash(manifest_path: Path = MANIFEST_PATH) -> str:
    payload = manifest_path.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def ingest_external(session: Session, manifest_path: Path = MANIFEST_PATH) -> ExternalIngestionRun:
    manifest_hash = compute_manifest_hash(manifest_path)
    existing = session.scalar(
        select(ExternalIngestionRun).where(
            ExternalIngestionRun.manifest_hash == manifest_hash,
            ExternalIngestionRun.status == ExternalIngestionStatus.SUCCESS.value,
        )
    )
    if existing is not None:
        return existing

    for model in (
        DocumentChunk,
        ProductHolding,
        EntityRelation,
        EntityAlias,
        Entity,
        SourceDocument,
        ExternalIngestionRun,
    ):
        session.execute(delete(model))
    session.flush()

    run = ExternalIngestionRun(
        manifest_hash=manifest_hash,
        status=ExternalIngestionStatus.RUNNING.value,
    )
    session.add(run)
    session.flush()

    embedder = DeterministicEmbeddingProvider()
    counts: dict[str, int] = {}

    try:
        documents = _load_jsonl(NORMALIZED_DIR / "source_documents.jsonl")
        for row in documents:
            session.add(
                SourceDocument(
                    document_id=row["document_id"],
                    source_type=row["source_type"],
                    title=row["title"],
                    publisher=row["publisher"],
                    published_at=_parse_date(row.get("published_at")),
                    effective_as_of=_parse_date(row.get("effective_as_of")),
                    collected_at=_parse_datetime(row["collected_at"]),
                    source_url=row.get("source_url"),
                    local_path=row["local_path"],
                    content_sha256=row["content_sha256"],
                    authority_rank=int(row.get("authority_rank", 1)),
                    usage_note=row.get("usage_note"),
                    parser_version=row["parser_version"],
                )
            )
        counts["source_document"] = len(documents)
        session.flush()

        entities = _load_jsonl(NORMALIZED_DIR / "entities.jsonl")
        for row in entities:
            session.add(Entity(**row))
        counts["entity"] = len(entities)

        aliases = _load_jsonl(NORMALIZED_DIR / "aliases.jsonl")
        for row in aliases:
            session.add(EntityAlias(**row))
        counts["entity_alias"] = len(aliases)

        holdings = _load_jsonl(NORMALIZED_DIR / "holdings.jsonl")
        for row in holdings:
            session.add(
                ProductHolding(
                    product_uid=row["product_uid"],
                    holding_entity_id=row["holding_entity_id"],
                    holding_name_raw=row["holding_name_raw"],
                    weight=row.get("weight"),
                    weight_unit=row.get("weight_unit"),
                    as_of_date=_parse_date(row.get("as_of_date")),
                    source_document_id=row["source_document_id"],
                    quality_flags=row.get("quality_flags", []),
                    coverage_status=row.get("coverage_status", "ACTIVE"),
                )
            )
        counts["product_holding"] = len(holdings)

        relations = _load_jsonl(NORMALIZED_DIR / "relations.jsonl")
        for row in relations:
            session.add(
                EntityRelation(
                    subject_entity_id=row["subject_entity_id"],
                    object_entity_id=row["object_entity_id"],
                    relation_type=row["relation_type"],
                    valid_from=_parse_date(row.get("valid_from")),
                    valid_to=_parse_date(row.get("valid_to")),
                    source_document_id=row["source_document_id"],
                    confidence_basis=row["confidence_basis"],
                    review_status=row.get("review_status", "APPROVED"),
                    quality_flags=row.get("quality_flags", []),
                )
            )
        counts["entity_relation"] = len(relations)
        session.flush()

        chunks = _load_jsonl(NORMALIZED_DIR / "document_chunks.jsonl")
        for row in chunks:
            embedding = embedder.embed(row["chunk_text"])
            session.add(
                DocumentChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    entity_ids=row.get("entity_ids", []),
                    chunk_text=row["chunk_text"],
                    token_count=row["token_count"],
                    embedding=embedding,
                    embedding_provider=embedder.provider,
                    embedding_model=embedder.model,
                    embedding_version=embedder.version,
                )
            )
        counts["document_chunk"] = len(chunks)

        run.row_counts = counts
        run.status = ExternalIngestionStatus.SUCCESS.value
        run.finished_at = datetime.now(UTC)
        session.commit()
        reloaded = session.get(ExternalIngestionRun, run.id)
        if reloaded is None:
            raise ExternalIngestionError("external ingestion run missing after commit")
        return reloaded
    except Exception:
        session.rollback()
        raise


def load_targets(path: Path = EXTERNAL_ROOT / "targets.yaml") -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return data
