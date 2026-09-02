from __future__ import annotations

import time

from sqlalchemy import or_, select

from app.embedding.deterministic import DeterministicEmbeddingProvider
from app.external.models import DocumentChunk, SourceDocument
from app.external.resolution import normalize_alias, resolve_entity_exact
from app.query.enums import Intent
from app.query.models import QuerySpec
from app.query.registry import get_field_registry
from app.query.validator import validate_queryspec_or_raise
from app.retrieval.federated_merger import build_retrieval_result
from app.retrieval.models import DocumentEvidence, RetrievalContext, RetrievalResult, SafeQueryPlan


class DocumentRetriever:
    def __init__(self, embedder: DeterministicEmbeddingProvider | None = None) -> None:
        self._embedder = embedder or DeterministicEmbeddingProvider()

    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        return self.retrieve_sync(spec, context)

    def retrieve_sync(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        started = time.perf_counter()
        registry = get_field_registry()
        validate_queryspec_or_raise(spec, registry)
        if spec.intent not in {Intent.EXPLAIN_TERM, Intent.RELATION_SEARCH}:
            msg = "DocumentRetriever requires EXPLAIN_TERM or RELATION_SEARCH intent"
            raise ValueError(msg)

        query_text = _resolve_query_text(spec)
        if not query_text:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return build_retrieval_result(
                spec=spec,
                plan=_empty_plan(spec),
                batches=[],
                candidates=[],
                elapsed_ms=elapsed_ms,
                warnings=["MISSING_QUERY_TEXT"],
            )

        session = context.session
        query_embedding = self._embedder.embed(query_text)
        embedding_version = self._embedder.version
        normalized_query = normalize_alias(query_text)
        resolved = resolve_entity_exact(session, query_text)
        resolved_ids = set(resolved.entity_ids)

        distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
        lexical_pattern = f"%{query_text.strip()}%"
        rows = session.execute(
            select(DocumentChunk, SourceDocument, distance_expr)
            .join(SourceDocument, SourceDocument.document_id == DocumentChunk.document_id)
            .where(
                DocumentChunk.embedding_version == embedding_version,
                DocumentChunk.embedding_provider == self._embedder.provider,
                SourceDocument.title.is_not(None),
                SourceDocument.publisher.is_not(None),
                SourceDocument.content_sha256.is_not(None),
                or_(
                    DocumentChunk.chunk_text.ilike(lexical_pattern),
                    DocumentChunk.embedding.is_not(None),
                ),
            )
            .order_by(distance_expr, DocumentChunk.chunk_id)
            .limit(spec.limit * 5)
        ).all()

        ranked: list[
            tuple[tuple[int, int, float, str], DocumentChunk, SourceDocument, float]
        ] = []
        for chunk, document, distance in rows:
            entity_hit = bool(resolved_ids.intersection(chunk.entity_ids))
            lexical_hit = normalized_query in normalize_alias(chunk.chunk_text)
            vector_score = 1.0 - float(distance)
            # hybrid: entity exact > lexical > vector, authority_rank tie-break
            stage = 0 if entity_hit else 1 if lexical_hit else 2
            sort_key = (stage, -document.authority_rank, -vector_score, chunk.chunk_id)
            ranked.append((sort_key, chunk, document, vector_score))

        ranked.sort(key=lambda item: item[0])
        evidences: list[DocumentEvidence] = []
        for _, chunk, document, vector_score in ranked[: spec.limit]:
            evidences.append(
                DocumentEvidence(
                    chunk_id=chunk.chunk_id,
                    document_id=document.document_id,
                    chunk_text=chunk.chunk_text,
                    source_title=document.title,
                    source_publisher=document.publisher,
                    source_url=document.source_url,
                    content_sha256=document.content_sha256,
                    score=round(vector_score, 6),
                    embedding_version=chunk.embedding_version,
                )
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return build_retrieval_result(
            spec=spec,
            plan=_empty_plan(spec),
            batches=[],
            candidates=[],
            elapsed_ms=elapsed_ms,
            document_evidences=evidences,
        )


def _resolve_query_text(spec: QuerySpec) -> str:
    if spec.entities:
        return spec.entities[0].text
    if spec.relationship_filters:
        return spec.relationship_filters[0].target_entity
    return ""


def _empty_plan(spec: QuerySpec) -> SafeQueryPlan:
    return SafeQueryPlan(
        product_families=list(spec.product_families),
        filters=[],
        sorts=[],
        limit=spec.limit,
        metrics=[],
    )
