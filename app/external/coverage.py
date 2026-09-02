from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.external.ingestion import load_targets
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


def build_coverage_report(session: Session) -> dict[str, Any]:
    targets = load_targets()
    p0_targets = targets.get("p0_targets", [])
    latest_run = session.scalar(
        select(ExternalIngestionRun)
        .where(ExternalIngestionRun.status == ExternalIngestionStatus.SUCCESS.value)
        .order_by(ExternalIngestionRun.id.desc())
    )
    counts = {
        "source_document": session.scalar(select(func.count()).select_from(SourceDocument)) or 0,
        "entity": session.scalar(select(func.count()).select_from(Entity)) or 0,
        "entity_alias": session.scalar(select(func.count()).select_from(EntityAlias)) or 0,
        "product_holding": session.scalar(
            select(func.count())
            .select_from(ProductHolding)
            .where(ProductHolding.coverage_status == "ACTIVE")
        )
        or 0,
        "entity_relation": session.scalar(
            select(func.count())
            .select_from(EntityRelation)
            .where(EntityRelation.review_status == "APPROVED")
        )
        or 0,
        "document_chunk": session.scalar(select(func.count()).select_from(DocumentChunk)) or 0,
    }
    unresolved_alias = session.scalar(
        select(func.count()).select_from(EntityAlias).where(EntityAlias.review_status != "APPROVED")
    ) or 0
    return {
        "latest_manifest_hash": latest_run.manifest_hash if latest_run else None,
        "row_counts": counts,
        "p0_targets": p0_targets,
        "unresolved_alias_count": unresolved_alias,
    }
