from __future__ import annotations

import time

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.curated.curated_models import ProductEtfKr
from app.data.repositories import ProductRepository
from app.external.models import EntityRelation, ProductHolding, SourceDocument
from app.external.resolution import EntityResolution, resolve_entity_exact
from app.query.enums import Intent, ProductFamily, RelationType
from app.query.models import QuerySpec
from app.query.registry import FieldRegistry, get_field_registry
from app.query.validator import validate_queryspec_or_raise
from app.retrieval.federated_merger import build_retrieval_result
from app.retrieval.filter_compiler import build_safe_plan
from app.retrieval.models import (
    Candidate,
    RelationEvidence,
    RetrievalContext,
    RetrievalResult,
    SafeQueryPlan,
)


def _family_prefix(family: ProductFamily) -> str:
    return f"{family.value}:"


def _matches_families(product_uid: str, families: list[ProductFamily]) -> bool:
    return any(product_uid.startswith(_family_prefix(family)) for family in families)


class RelationRetriever:
    def __init__(self, repository: ProductRepository | None = None) -> None:
        self._repository = repository or ProductRepository()

    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        return self.retrieve_sync(spec, context)

    def retrieve_sync(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        started = time.perf_counter()
        registry = get_field_registry()
        validate_queryspec_or_raise(spec, registry)
        if spec.intent != Intent.RELATION_SEARCH:
            msg = "RelationRetriever requires RELATION_SEARCH intent"
            raise ValueError(msg)

        session = context.session
        warnings: list[str] = []
        evidences: list[RelationEvidence] = []
        holding_uids: list[str] = []

        for clause in spec.relationship_filters:
            resolution = resolve_entity_exact(session, clause.target_entity)
            if resolution.unresolved:
                warnings.append(f"UNRESOLVED_ENTITY:{clause.target_entity}")
                continue
            if resolution.ambiguous:
                warnings.append(f"AMBIGUOUS_ENTITY:{clause.target_entity}")
                continue

            if clause.relation == RelationType.HOLDS:
                holding_evidences = self._query_holdings(
                    session,
                    resolution=resolution,
                    families=spec.product_families,
                )
                evidences.extend(holding_evidences)
                holding_uids.extend(
                    item.product_uid for item in holding_evidences if item.product_uid is not None
                )
            else:
                evidences.extend(
                    self._query_relations(
                        session,
                        resolution=resolution,
                        relation_type=clause.relation.value,
                        match_method=resolution.match_method,
                    )
                )

        candidates = self._load_holding_candidates(
            session,
            spec=spec,
            dataset_version_id=context.dataset_version_id,
            product_uids=self._resolve_holding_product_uids(
                session,
                dataset_version_id=context.dataset_version_id,
                evidences=evidences,
                product_uids=holding_uids,
            ),
            registry=registry,
        )
        if candidates:
            selected_uids = {item.product_uid for item in candidates}
            evidences = [
                item
                for item in evidences
                if item.product_uid in selected_uids or not item.product_uid
            ]
        evidences = evidences[: spec.limit]
        candidates = candidates[: spec.limit]
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return build_retrieval_result(
            spec=spec,
            plan=_empty_plan(spec),
            batches=[],
            candidates=candidates,
            elapsed_ms=elapsed_ms,
            warnings=warnings,
            relation_evidences=evidences,
        )

    def _query_holdings(
        self,
        session: Session,
        *,
        resolution: EntityResolution,
        families: list[ProductFamily],
    ) -> list[RelationEvidence]:
        rows = session.execute(
            select(ProductHolding, SourceDocument)
            .join(SourceDocument, SourceDocument.document_id == ProductHolding.source_document_id)
            .where(
                ProductHolding.holding_entity_id.in_(resolution.entity_ids),
                ProductHolding.coverage_status == "ACTIVE",
            )
            .order_by(ProductHolding.product_uid, ProductHolding.as_of_date.desc())
        ).all()

        evidences: list[RelationEvidence] = []
        for holding, document in rows:
            if not _matches_families(holding.product_uid, families):
                continue
            if any(flag for flag in holding.quality_flags if flag.startswith("UNIT_")):
                continue
            evidence = RelationEvidence(
                relation_type=RelationType.HOLDS.value,
                subject_entity_id=holding.product_uid,
                object_entity_id=holding.holding_entity_id,
                source_document_id=document.document_id,
                source_title=document.title,
                source_publisher=document.publisher,
                source_url=document.source_url,
                content_sha256=document.content_sha256,
                as_of_date=holding.as_of_date,
                quality_flags=list(holding.quality_flags),
                coverage_status=holding.coverage_status,
                product_uid=holding.product_uid,
                holding_name_raw=holding.holding_name_raw,
                weight=holding.weight,
                weight_unit=holding.weight_unit,
                match_method=resolution.match_method,
            )
            evidences.append(evidence)
        return evidences

    @staticmethod
    def _resolve_holding_product_uids(
        session: Session,
        *,
        dataset_version_id: int,
        evidences: list[RelationEvidence],
        product_uids: list[str],
    ) -> list[str]:
        """외부 snapshot의 국내 ETF ticker UID를 Curated ISIN UID로 결합한다."""
        ticker_by_external_uid = {
            uid: uid.split(":", 1)[1]
            for uid in product_uids
            if uid.startswith("ETF_KR:") and ":" in uid
        }
        if not ticker_by_external_uid:
            return product_uids
        rows = session.execute(
            select(ProductEtfKr.pd_ticker, ProductEtfKr.product_uid).where(
                ProductEtfKr.dataset_version_id == dataset_version_id,
                ProductEtfKr.pd_ticker.in_(list(ticker_by_external_uid.values())),
            )
        ).all()
        uid_by_ticker = {ticker: uid for ticker, uid in rows if ticker and uid}
        canonical_by_external_uid = {
            external_uid: uid_by_ticker[ticker]
            for external_uid, ticker in ticker_by_external_uid.items()
            if ticker in uid_by_ticker
        }
        for evidence in evidences:
            if evidence.product_uid in canonical_by_external_uid:
                evidence.product_uid = canonical_by_external_uid[evidence.product_uid]
        return [canonical_by_external_uid.get(uid, uid) for uid in product_uids]

    def _load_holding_candidates(
        self,
        session: Session,
        *,
        spec: QuerySpec,
        dataset_version_id: int,
        product_uids: list[str],
        registry: FieldRegistry,
    ) -> list[Candidate]:
        """외부 보유 근거의 UID를 Curated 원천 행으로 재해석해 Evidence 역검증을 가능하게 한다."""
        plan = build_safe_plan(spec, get_field_registry())
        candidates: list[Candidate] = []
        for family in spec.product_families:
            family_uids = [
                uid for uid in dict.fromkeys(product_uids) if uid.startswith(_family_prefix(family))
            ]
            batch = self._repository.query(
                session,
                family=family,
                plan=plan,
                dataset_version_id=dataset_version_id,
                product_uids=family_uids,
                registry=registry,
            )
            for candidate in batch.candidates:
                candidate.selection_reasons.append("RELATION_HOLDS")
            candidates.extend(batch.candidates)
        return candidates

    def _query_relations(
        self,
        session: Session,
        *,
        resolution: EntityResolution,
        relation_type: str,
        match_method: str | None,
    ) -> list[RelationEvidence]:
        rows = session.execute(
            select(EntityRelation, SourceDocument)
            .join(SourceDocument, SourceDocument.document_id == EntityRelation.source_document_id)
            .where(
                EntityRelation.relation_type == relation_type,
                EntityRelation.review_status == "APPROVED",
                or_(
                    EntityRelation.subject_entity_id.in_(resolution.entity_ids),
                    EntityRelation.object_entity_id.in_(resolution.entity_ids),
                ),
            )
            .order_by(EntityRelation.subject_entity_id, EntityRelation.object_entity_id)
        ).all()

        evidences: list[RelationEvidence] = []
        for relation, document in rows:
            if relation.confidence_basis == "FUZZY_ONLY":
                continue
            evidences.append(
                RelationEvidence(
                    relation_type=relation.relation_type,
                    subject_entity_id=relation.subject_entity_id,
                    object_entity_id=relation.object_entity_id,
                    source_document_id=document.document_id,
                    source_title=document.title,
                    source_publisher=document.publisher,
                    source_url=document.source_url,
                    content_sha256=document.content_sha256,
                    as_of_date=relation.valid_from,
                    quality_flags=list(relation.quality_flags),
                    match_method=match_method,
                    confidence_basis=relation.confidence_basis,
                )
            )
        return evidences


def _empty_plan(spec: QuerySpec) -> SafeQueryPlan:
    return SafeQueryPlan(
        product_families=list(spec.product_families),
        filters=[],
        sorts=[],
        limit=spec.limit,
        metrics=[],
    )
