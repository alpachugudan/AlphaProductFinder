from __future__ import annotations

from app.evidence.models import EvidenceBundle, RelationshipEvidenceItem


def serialize_retrieved_context(
    bundles: list[EvidenceBundle],
    *,
    relationship_evidence: list[RelationshipEvidenceItem] | None = None,
    char_budget: int = 8000,
) -> str:
    lines: list[str] = []
    original_count = len(bundles)
    truncated = False

    for bundle in sorted(bundles, key=lambda item: item.product_uid):
        line = _serialize_bundle(bundle)
        projected = "\n".join(lines + [line])
        if len(projected.encode("utf-8")) > char_budget:
            truncated = True
            break
        lines.append(line)

    for relation in relationship_evidence or []:
        line = _serialize_standalone_relation(relation)
        projected = "\n".join(lines + [line])
        if len(projected.encode("utf-8")) > char_budget:
            truncated = True
            break
        lines.append(line)

    if truncated:
        lines.append(f"meta=truncated;original_count={original_count};included_count={len(lines)}")
    elif not lines:
        lines.append("meta=empty;original_count=0")

    return "\n".join(lines)


def _serialize_bundle(bundle: EvidenceBundle) -> str:
    name = _escape(bundle.product_name or "")
    header = (
        f"[{bundle.source_table}|key={_escape(bundle.source_key)}|uid={bundle.product_uid}|name={name}]"
    )
    field_parts: list[str] = []
    for field in bundle.used_fields:
        unit = field.unit or ""
        as_of = field.as_of_date or "none"
        quality = ",".join(field.quality_flags) if field.quality_flags else "none"
        field_parts.append(
            f"{field.logical_field}({field.source_field}):{field.value}{unit}:as_of={as_of}:quality={quality}"
        )
    fields = ";".join(field_parts) if field_parts else "none"
    reasons = ",".join(bundle.selection_reasons) if bundle.selection_reasons else "none"
    source_docs = _serialize_source_docs(bundle)
    quality = ",".join(bundle.quality_flags) or "none"
    return (
        f"{header}\nfields={fields};\nquality={quality};\nreason={reasons};\nsource_docs={source_docs}"
    )


def _serialize_source_docs(bundle: EvidenceBundle) -> str:
    docs: list[str] = []
    for relation in bundle.relationship_evidence:
        docs.append(
            "|".join(
                [
                    relation.source_document_id,
                    _escape(relation.source_title),
                    _escape(relation.source_publisher),
                    relation.as_of_date or "none",
                    relation.source_url or "none",
                    relation.content_sha256,
                ]
            )
        )
    for document in bundle.document_evidence:
        docs.append(
            "|".join(
                [
                    document.document_id,
                    _escape(document.source_title),
                    _escape(document.source_publisher),
                    "none",
                    document.source_url or "none",
                    document.content_sha256,
                ]
            )
        )
    return ";".join(docs) if docs else "none"


def _serialize_standalone_relation(relation: RelationshipEvidenceItem) -> str:
    return (
        "[RELATION"
        f"|type={relation.relation_type}"
        f"|subject={_escape(relation.subject_entity_id)}"
        f"|object={_escape(relation.object_entity_id)}]"
        "\nsource_docs="
        + "|".join(
            [
                relation.source_document_id,
                _escape(relation.source_title),
                _escape(relation.source_publisher),
                relation.as_of_date or "none",
                relation.source_url or "none",
                relation.content_sha256,
            ]
        )
    )


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "\\n").replace(";", "\\;")
