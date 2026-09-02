from __future__ import annotations

import sys
from dataclasses import dataclass

from app.query.registry import (
    FIELD_REGISTRY_PATH,
    SYNONYMS_PATH,
    TTL_FILES,
    load_field_registry,
    load_synonyms,
)
from rdflib import Graph

BLOCKED_SOURCE_FIELDS = frozenset({"buyable_quantity", "fd_wk1_ern_r"})


@dataclass(slots=True)
class OntologyValidationReport:
    ttl_files: int
    field_count: int
    synonym_concepts: int
    errors: list[str]


def validate_ontology() -> OntologyValidationReport:
    errors: list[str] = []

    for ttl_path in TTL_FILES:
        if not ttl_path.exists():
            errors.append(f"missing ttl file: {ttl_path.name}")
            continue
        graph = Graph()
        try:
            graph.parse(ttl_path, format="turtle")
        except Exception as exc:
            errors.append(f"invalid ttl {ttl_path.name}: {exc}")

    registry = load_field_registry()
    for field in registry.fields.values():
        for mapping in field.families.values():
            if mapping.source_field in BLOCKED_SOURCE_FIELDS:
                errors.append(
                    f"blocked source field in registry: {field.id} -> {mapping.source_field}"
                )

    synonyms = load_synonyms()
    alias_index: dict[str, set[str]] = {}
    for canonical_id, groups in synonyms.items():
        for alias in groups.get("ko", []) + groups.get("en", []):
            alias_index.setdefault(alias.strip().lower(), set()).add(canonical_id)
    for alias, concepts in alias_index.items():
        if len(concepts) > 1:
            errors.append(f"ambiguous synonym alias: {alias} -> {sorted(concepts)}")

    if not FIELD_REGISTRY_PATH.exists():
        errors.append("missing field_registry.yaml")
    if not SYNONYMS_PATH.exists():
        errors.append("missing synonyms.yaml")

    return OntologyValidationReport(
        ttl_files=len(TTL_FILES),
        field_count=len(registry.fields),
        synonym_concepts=len(synonyms),
        errors=errors,
    )


def main() -> int:
    report = validate_ontology()
    if report.errors:
        print("Ontology validation FAILED", file=sys.stderr)
        for error in report.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Ontology validation OK")
    print(f"  ttl_files: {report.ttl_files}")
    print(f"  field_count: {report.field_count}")
    print(f"  synonym_concepts: {report.synonym_concepts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
