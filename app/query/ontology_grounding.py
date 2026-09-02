from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from app.query.enums import GroundingRule
from app.query.registry import load_synonyms


@dataclass(frozen=True, slots=True)
class GroundingMatch:
    token: str
    canonical_id: str
    rule: GroundingRule


@dataclass(frozen=True, slots=True)
class AmbiguousGrounding:
    token: str
    candidates: tuple[str, ...]
    code: str = "AMBIGUOUS_GROUNDING"


GroundingResult = GroundingMatch | AmbiguousGrounding


def normalize_token(text: str) -> str:
    """Unicode NFKC + trim + 연속 공백 축소 + 영문 소문자"""
    normalized = unicodedata.normalize("NFKC", text).strip()
    collapsed = " ".join(normalized.split())
    return collapsed.lower()


@lru_cache
def _build_synonym_index() -> dict[str, set[str]]:
    raw = load_synonyms()
    index: dict[str, set[str]] = {}
    for canonical_id, groups in raw.items():
        for alias in groups.get("ko", []) + groups.get("en", []):
            index.setdefault(normalize_token(alias), set()).add(canonical_id)
        index.setdefault(normalize_token(canonical_id), set()).add(canonical_id)
    return index


def ground_token(token: str) -> GroundingResult:
    normalized = normalize_token(token)
    if not normalized:
        return AmbiguousGrounding(token=token, candidates=())

    index = _build_synonym_index()
    candidates = tuple(sorted(index.get(normalized, set())))
    if len(candidates) == 1:
        rule = (
            GroundingRule.EXACT
            if normalized == normalize_token(candidates[0])
            else GroundingRule.SYNONYM
        )
        return GroundingMatch(token=token, canonical_id=candidates[0], rule=rule)
    if len(candidates) > 1:
        return AmbiguousGrounding(token=token, candidates=candidates)
    return AmbiguousGrounding(token=token, candidates=())


def ground_phrase(text: str) -> list[GroundingResult]:
    return [ground_token(part) for part in text.split() if part.strip()]
