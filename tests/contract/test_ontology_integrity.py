from __future__ import annotations

from scripts.validate_ontology import validate_ontology


def test_validate_ontology_passes() -> None:
    report = validate_ontology()
    assert report.errors == []
    assert report.ttl_files == 5
    assert report.field_count >= 20
    assert report.synonym_concepts >= 10
