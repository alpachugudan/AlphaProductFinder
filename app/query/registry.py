from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from app.config.settings import PROJECT_ROOT
from app.query.enums import Operator, ProductFamily

ValueType = Literal["string", "decimal", "integer", "date", "boolean"]
Coverage = Literal["full", "partial", "none"]

ONTOLOGY_ROOT = PROJECT_ROOT / "ontology"
FIELD_REGISTRY_PATH = ONTOLOGY_ROOT / "mappings" / "field_registry.yaml"
SYNONYMS_PATH = ONTOLOGY_ROOT / "mappings" / "synonyms.yaml"

TTL_FILES = (
    ONTOLOGY_ROOT / "common.ttl",
    ONTOLOGY_ROOT / "bond_kr.ttl",
    ONTOLOGY_ROOT / "etf_kr.ttl",
    ONTOLOGY_ROOT / "etf_gl.ttl",
    ONTOLOGY_ROOT / "fund_pub.ttl",
)


@dataclass(frozen=True, slots=True)
class FamilyFieldMapping:
    source_field: str
    date_field: str | None
    coverage: Coverage
    comparable_scope: str
    filterable: bool = True
    sortable: bool = True


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    id: str
    label_ko: str
    value_type: ValueType
    unit: str | None
    families: dict[ProductFamily, FamilyFieldMapping]
    operators: tuple[Operator, ...]
    quality_exclusions: tuple[str, ...]
    filterable: bool = True
    sortable: bool = True
    aggregate_allowed: bool = False
    rank_blocked: bool = False
    requires_period: bool = False


class FieldRegistry:
    def __init__(self, fields: dict[str, FieldDefinition]) -> None:
        self._fields = fields

    @property
    def fields(self) -> dict[str, FieldDefinition]:
        return self._fields

    def get(self, field_id: str) -> FieldDefinition | None:
        return self._fields.get(field_id)

    def supports_family(self, field_id: str, family: ProductFamily) -> bool:
        field = self._fields.get(field_id)
        return field is not None and family in field.families

    def blocked_field_ids(self) -> frozenset[str]:
        return frozenset(field_id for field_id, field in self._fields.items() if field.rank_blocked)


def _parse_operators(raw: list[str]) -> tuple[Operator, ...]:
    return tuple(Operator(item) for item in raw)


def _parse_families(raw: dict[str, Any]) -> dict[ProductFamily, FamilyFieldMapping]:
    parsed: dict[ProductFamily, FamilyFieldMapping] = {}
    for family_name, mapping in raw.items():
        coverage_raw = str(mapping.get("coverage", "full"))
        parsed[ProductFamily(family_name)] = FamilyFieldMapping(
            source_field=str(mapping["source_field"]),
            date_field=mapping.get("date_field"),
            coverage=coverage_raw,  # type: ignore[arg-type]
            comparable_scope=str(mapping.get("comparable_scope", "within_family")),
            filterable=bool(mapping.get("filterable", True)),
            sortable=bool(mapping.get("sortable", True)),
        )
    return parsed


def load_field_registry(path: Path = FIELD_REGISTRY_PATH) -> FieldRegistry:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fields: dict[str, FieldDefinition] = {}
    for item in data["fields"]:
        field_id = str(item["id"])
        fields[field_id] = FieldDefinition(
            id=field_id,
            label_ko=str(item["label_ko"]),
            value_type=item["value_type"],
            unit=item.get("unit"),
            families=_parse_families(item["families"]),
            operators=_parse_operators(item["operators"]),
            quality_exclusions=tuple(item.get("quality_exclusions", [])),
            filterable=bool(item.get("filterable", True)),
            sortable=bool(item.get("sortable", True)),
            aggregate_allowed=bool(item.get("aggregate_allowed", False)),
            rank_blocked=bool(item.get("rank_blocked", False)),
            requires_period=bool(item.get("requires_period", False)),
        )
    return FieldRegistry(fields)


@lru_cache
def get_field_registry() -> FieldRegistry:
    return load_field_registry()


def load_synonyms(path: Path = SYNONYMS_PATH) -> dict[str, dict[str, list[str]]]:
    return cast(dict[str, dict[str, list[str]]], yaml.safe_load(path.read_text(encoding="utf-8")))
