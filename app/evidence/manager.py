from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.reason_codes import ReasonCode
from app.core.errors import ProductFinderError
from app.curated.curated_models import (
    ProductBondKr,
    ProductEnvelopeMixin,
    ProductEtfGlobal,
    ProductEtfKr,
    ProductFundPublic,
)
from app.evidence.models import (
    CandidateValidationOutcome,
    EvidenceBundle,
    EvidenceValidationAction,
    EvidenceValidationResult,
    RelationshipEvidenceItem,
    compute_evidence_hash,
)
from app.external.models import SourceDocument
from app.query.enums import ProductFamily
from app.query.registry import get_field_registry
from app.retrieval.column_map import resolve_column

SOURCE_TABLE_MODELS: dict[str, type[ProductEnvelopeMixin]] = {
    "PRBD01N001": ProductBondKr,
    "PREF01N001": ProductEtfKr,
    "PREF02N001": ProductEtfGlobal,
    "PRFD01N001": ProductFundPublic,
}


class EvidenceIntegrityError(ProductFinderError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="EVIDENCE_INTEGRITY_ERROR")


class EvidenceManager:
    def validate_relationship_evidence(
        self,
        session: Session,
        relations: list[RelationshipEvidenceItem],
    ) -> None:
        """상품 후보가 없는 기업 관계 답변도 동결된 공식 문서로 역검증한다."""
        for relation in relations:
            if not relation.source_document_id or not relation.content_sha256:
                msg = "relation source metadata incomplete"
                raise EvidenceIntegrityError(msg)
            document = session.scalar(
                select(SourceDocument).where(
                    SourceDocument.document_id == relation.source_document_id,
                    SourceDocument.content_sha256 == relation.content_sha256,
                )
            )
            if document is None:
                msg = f"missing source_document: {relation.source_document_id}"
                raise EvidenceIntegrityError(msg)

    def validate(
        self,
        session: Session,
        *,
        dataset_version_id: int,
        bundles: list[EvidenceBundle],
    ) -> EvidenceValidationResult:
        outcomes: list[CandidateValidationOutcome] = []
        validated: list[EvidenceBundle] = []
        reason_codes: list[ReasonCode] = []
        warnings: list[str] = []

        for bundle in bundles:
            try:
                self._validate_bundle(session, dataset_version_id=dataset_version_id, bundle=bundle)
            except EvidenceIntegrityError as exc:
                outcomes.append(
                    CandidateValidationOutcome(
                        product_uid=bundle.product_uid,
                        action=EvidenceValidationAction.DROP_CANDIDATE,
                        reason=str(exc),
                    )
                )
                continue

            relation_ok, relation_reason = self._validate_relationships(session, bundle)
            if not relation_ok:
                outcomes.append(
                    CandidateValidationOutcome(
                        product_uid=bundle.product_uid,
                        action=EvidenceValidationAction.DROP_CANDIDATE,
                        reason=relation_reason,
                    )
                )
                reason_codes.append(ReasonCode.EXTERNAL_EVIDENCE_MISSING)
                continue

            validated.append(bundle)
            if bundle.quality_flags:
                warnings.append(f"quality_flags:{bundle.product_uid}={','.join(bundle.quality_flags)}")

        evidence_hash = compute_evidence_hash(validated)
        passed = len(validated) > 0 or len(bundles) == 0
        return EvidenceValidationResult(
            outcomes=outcomes,
            bundles=validated,
            evidence_hash=evidence_hash,
            passed=passed,
            reason_codes=_dedupe(reason_codes),
            warnings=warnings,
        )

    def _validate_bundle(
        self,
        session: Session,
        *,
        dataset_version_id: int,
        bundle: EvidenceBundle,
    ) -> None:
        model = SOURCE_TABLE_MODELS.get(bundle.source_table)
        if model is None:
            msg = f"unknown source_table: {bundle.source_table}"
            raise EvidenceIntegrityError(msg)

        row = session.scalar(
            select(model).where(
                model.dataset_version_id == dataset_version_id,
                model.product_uid == bundle.product_uid,
                model.source_key == bundle.source_key,
            )
        )
        if row is None:
            msg = f"curated row missing for uid={bundle.product_uid}"
            raise EvidenceIntegrityError(msg)

        if bundle.product_name and row.product_name and bundle.product_name != row.product_name:
            msg = f"product_name mismatch for uid={bundle.product_uid}"
            raise EvidenceIntegrityError(msg)

        registry = get_field_registry()
        for field in bundle.used_fields:
            family = ProductFamily(bundle.product_uid.split(":", 1)[0])
            try:
                column = resolve_column(family, field.logical_field, registry)
            except KeyError as exc:
                msg = f"unknown logical field: {field.logical_field}"
                raise EvidenceIntegrityError(msg) from exc
            stored_raw = getattr(row, column.key)
            if stored_raw is None and field.value is not None:
                msg = f"metric missing on row: {field.logical_field}"
                raise EvidenceIntegrityError(msg)
            if stored_raw is not None and field.value is not None:
                if _stringify_numeric(stored_raw) != field.value and str(stored_raw) != field.value:
                    msg = f"metric value mismatch: {field.logical_field}"
                    raise EvidenceIntegrityError(msg)

    def _validate_relationships(
        self,
        session: Session,
        bundle: EvidenceBundle,
    ) -> tuple[bool, str]:
        try:
            self.validate_relationship_evidence(session, bundle.relationship_evidence)
        except EvidenceIntegrityError as exc:
            return False, str(exc)
        return True, ""


def _stringify_numeric(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        return format(value, "f")
    return str(value)


def _dedupe(codes: list[ReasonCode]) -> list[ReasonCode]:
    seen: set[ReasonCode] = set()
    ordered: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered
