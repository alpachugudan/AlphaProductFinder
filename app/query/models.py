from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.query.enums import (
    AsOfRequirement,
    Direction,
    EntityType,
    Intent,
    MissingPolicy,
    Operator,
    ProductFamily,
    RelationType,
)


class EntityClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    entity_type: EntityType


class FilterClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    operator: Operator
    value: Any | None = None


class RelationshipFilterClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation: RelationType
    target_entity: str


class PreferenceClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    direction: Direction
    priority: int | None = None

    @field_validator("priority")
    @classmethod
    def priority_must_be_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            msg = "priority must be a positive integer"
            raise ValueError(msg)
        return value


class SortClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    direction: Direction


class QuerySpec(BaseModel):
    """SQL·테이블·원천 컬럼을 받지 않는 실행 계약"""

    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    intent: Intent
    product_families: list[ProductFamily] = Field(default_factory=list)
    entities: list[EntityClause] = Field(default_factory=list)
    filters: list[FilterClause] = Field(default_factory=list)
    relationship_filters: list[RelationshipFilterClause] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    preferences: list[PreferenceClause] = Field(default_factory=list)
    sort: list[SortClause] = Field(default_factory=list)
    limit: int = 5
    as_of_requirement: AsOfRequirement = AsOfRequirement.SHOW_FIELD_DATE
    missing_policy: MissingPolicy = MissingPolicy.EXCLUDE_AND_DISCLOSE

    @field_validator("product_families")
    @classmethod
    def dedupe_families_preserve_order(
        cls, value: list[ProductFamily]
    ) -> list[ProductFamily]:
        seen: set[ProductFamily] = set()
        deduped: list[ProductFamily] = []
        for family in value:
            if family not in seen:
                seen.add(family)
                deduped.append(family)
        return deduped

    @model_validator(mode="after")
    def validate_families_for_intent(self) -> QuerySpec:
        if self.intent == Intent.UNSUPPORTED_PREDICTION:
            return self
        if not 1 <= len(self.product_families) <= 4:
            msg = "product_families must contain 1 to 4 items"
            raise ValueError(msg)
        return self

    @field_validator("limit")
    @classmethod
    def limit_in_range(cls, value: int) -> int:
        if not 1 <= value <= 10:
            msg = "limit must be between 1 and 10"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_preference_priority_conflicts(self) -> QuerySpec:
        seen: dict[int, str] = {}
        for pref in self.preferences:
            if pref.priority is None:
                continue
            if pref.priority in seen:
                msg = f"duplicate preference priority: {pref.priority}"
                raise ValueError(msg)
            seen[pref.priority] = pref.field
        return self

    @model_validator(mode="after")
    def validate_sort_preference_conflicts(self) -> QuerySpec:
        sort_map = {item.field: item.direction for item in self.sort}
        for pref in self.preferences:
            if pref.field in sort_map and sort_map[pref.field] != pref.direction:
                msg = f"sort and preferences conflict on field: {pref.field}"
                raise ValueError(msg)
        return self
