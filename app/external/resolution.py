from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.external.models import Entity, EntityAlias


def normalize_alias(text: str) -> str:
    return " ".join(text.strip().lower().split())


@dataclass(slots=True)
class EntityResolution:
    target_text: str
    entity_ids: list[str] = field(default_factory=list)
    match_method: str | None = None
    unresolved: bool = False
    ambiguous: bool = False


def resolve_entity_exact(session: Session, target_text: str) -> EntityResolution:
    """fuzzy-only 자동 승인 금지 — exact alias·canonical name만 허용"""
    normalized = normalize_alias(target_text)
    alias_rows = session.scalars(
        select(EntityAlias.entity_id)
        .where(
            EntityAlias.normalized_alias == normalized,
            EntityAlias.review_status == "APPROVED",
            EntityAlias.match_method == "EXACT",
        )
        .order_by(EntityAlias.entity_id)
    ).all()
    if alias_rows:
        unique = sorted(set(alias_rows))
        return EntityResolution(
            target_text=target_text,
            entity_ids=unique,
            match_method="ALIAS_EXACT",
            ambiguous=len(unique) > 1,
        )

    canonical_rows = session.scalars(
        select(Entity.entity_id)
        .where(func.lower(Entity.canonical_name) == normalized)
        .order_by(Entity.entity_id)
    ).all()
    if canonical_rows:
        unique = sorted(set(canonical_rows))
        return EntityResolution(
            target_text=target_text,
            entity_ids=unique,
            match_method="CANONICAL_EXACT",
            ambiguous=len(unique) > 1,
        )

    return EntityResolution(target_text=target_text, unresolved=True)
