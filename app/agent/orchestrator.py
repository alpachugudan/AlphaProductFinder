from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from app.agent.decision import Decision, DecisionState
from app.agent.execution_plan import ExecutionPlan, RetrieverKind
from app.agent.merger import merge_retrieval_results
from app.agent.policy_engine import decide_preliminary, validate_and_plan
from app.agent.reason_codes import ReasonCode
from app.config.settings import Settings, get_settings
from app.core.cache import BoundedVersionedCache, queryspec_cache_key, retrieval_cache_key
from app.core.errors import RetrieverFailure
from app.evidence.models import EvidenceValidationResult
from app.llm.factory import get_llm_provider
from app.query.models import QuerySpec
from app.query.ontology_grounding import ground_phrase
from app.retrieval.document_retriever import DocumentRetriever
from app.retrieval.models import RetrievalContext, RetrievalResult
from app.retrieval.relation_retriever import RelationRetriever
from app.retrieval.sql_retriever import SqlRetriever


class SqlRetrieverProtocol(Protocol):
    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult: ...


class RelationRetrieverProtocol(Protocol):
    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult: ...


class DocumentRetrieverProtocol(Protocol):
    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult: ...


@dataclass(slots=True)
class TraceEvent:
    stage: str
    detail: str
    elapsed_ms: int = 0
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRunResult:
    query_id: str
    spec: QuerySpec
    execution_plan: ExecutionPlan | None
    merged_result: RetrievalResult | None
    sql_result: RetrievalResult | None
    relation_result: RetrievalResult | None
    document_result: RetrievalResult | None
    preliminary_decision: Decision
    evidence_requirements: list[str]
    trace_events: list[TraceEvent]


def finalize_decision(
    preliminary: Decision,
    evidence_validation: EvidenceValidationResult,
) -> Decision:
    """Step 08 Evidence 검증 뒤 최종 ANSWER/ABSTAIN 확정"""
    if preliminary.state not in {DecisionState.PRE_ANSWER, DecisionState.ANSWER}:
        return preliminary

    remaining = [
        uid
        for uid in preliminary.selected_candidate_ids
        if uid not in evidence_validation.blocked_product_uids
    ]
    if remaining:
        reason_codes = list(preliminary.reason_codes)
        if evidence_validation.blocked_product_uids:
            reason_codes.append(ReasonCode.PARTIAL_CANDIDATE_REMOVED)
        return Decision(
            state=DecisionState.ANSWER,
            reason_codes=_dedupe_reason_codes(reason_codes + [ReasonCode.EVIDENCE_READY]),
            selected_candidate_ids=remaining,
            warnings=preliminary.warnings,
            execution_summary={
                **preliminary.execution_summary,
                "finalized": True,
                "removed_count": len(evidence_validation.blocked_product_uids),
            },
        )

    codes = _dedupe_reason_codes(
        list(evidence_validation.reason_codes) + [ReasonCode.QUALITY_BLOCKED]
    )
    return Decision(
        state=DecisionState.ABSTAIN,
        reason_codes=codes,
        warnings=preliminary.warnings,
        execution_summary={**preliminary.execution_summary, "finalized": True},
    )


class AgentOrchestrator:
    def __init__(
        self,
        *,
        sql_retriever: SqlRetrieverProtocol | None = None,
        relation_retriever: RelationRetrieverProtocol | None = None,
        document_retriever: DocumentRetrieverProtocol | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._sql = sql_retriever or SqlRetriever()
        self._relation = relation_retriever or RelationRetriever()
        self._document = document_retriever or DocumentRetriever()
        self._settings = settings or get_settings()
        self._queryspec_cache: BoundedVersionedCache[QuerySpec] = BoundedVersionedCache(
            max_entries=self._settings.cache_capacity
        )
        self._retrieval_cache: BoundedVersionedCache[AgentRunResult] = BoundedVersionedCache(
            max_entries=self._settings.cache_capacity
        )

    async def run_with_question(
        self,
        question: str,
        context: RetrievalContext,
    ) -> AgentRunResult:
        provider = get_llm_provider(self._settings)
        cache_key = queryspec_cache_key(
            question,
            prompt_version=getattr(provider, "prompt_version", "provider-v1"),
            schema_version="queryspec-1.0",
        )
        spec = self._queryspec_cache.get(cache_key)
        if spec is None:
            spec = await provider.parse_query(question)
            self._queryspec_cache.put(cache_key, spec)
        return await self.run_with_spec(spec, context)

    async def run_with_spec(
        self,
        spec: QuerySpec,
        context: RetrievalContext,
    ) -> AgentRunResult:
        cache_key = retrieval_cache_key(
            spec.model_dump(mode="json"),
            dataset_version=context.dataset_version_label,
            external_version=context.external_version,
        )
        cached = self._retrieval_cache.get(cache_key)
        if cached is not None:
            return cached

        trace: list[TraceEvent] = []
        started = time.perf_counter()
        grounding = ground_phrase(" ".join(entity.text for entity in spec.entities))
        early, plan = validate_and_plan(
            spec,
            dataset_version_label=context.dataset_version_label,
            grounding_results=grounding,
        )
        trace.append(
            TraceEvent(
                stage="VALIDATE",
                detail="validation_complete",
                elapsed_ms=_elapsed(started),
            )
        )
        if early is not None or plan is None:
            result = AgentRunResult(
                query_id=str(uuid4_fallback(spec)),
                spec=spec,
                execution_plan=None,
                merged_result=None,
                sql_result=None,
                relation_result=None,
                document_result=None,
                preliminary_decision=early
                or Decision(
                    state=DecisionState.ABSTAIN,
                    reason_codes=[ReasonCode.VALIDATION_FAILED],
                ),
                evidence_requirements=[],
                trace_events=trace,
            )
            self._retrieval_cache.put(cache_key, result)
            return result

        sql_result: RetrievalResult | None = None
        relation_result: RetrievalResult | None = None
        document_result: RetrievalResult | None = None

        for sub_plan in plan.retrievers:
            retriever_started = time.perf_counter()
            try:
                if sub_plan.kind == RetrieverKind.SQL:
                    sql_result = await self._sql.retrieve(spec, context)
                elif sub_plan.kind == RetrieverKind.RELATION:
                    relation_result = await self._relation.retrieve(spec, context)
                elif sub_plan.kind == RetrieverKind.DOCUMENT:
                    document_result = await self._document.retrieve(spec, context)
            except Exception as exc:
                if sub_plan.required:
                    raise RetrieverFailure(sub_plan.kind.value, str(exc)) from exc
                trace.append(
                    TraceEvent(
                        stage="RETRIEVE",
                        detail=f"optional_{sub_plan.kind.value}_failed",
                        elapsed_ms=_elapsed(retriever_started),
                    )
                )
                continue
            trace.append(
                TraceEvent(
                    stage="RETRIEVE",
                    detail=sub_plan.kind.value,
                    elapsed_ms=_elapsed(retriever_started),
                    counts={
                        "candidates": _candidate_count(
                            sub_plan.kind, sql_result, relation_result, document_result
                        )
                    },
                )
            )

        merged = merge_retrieval_results(
            spec=spec,
            merge_mode=plan.merge_mode,
            sql_result=sql_result,
            relation_result=relation_result,
            document_result=document_result,
        )
        trace.append(
            TraceEvent(
                stage="MERGE",
                detail=plan.merge_mode.value,
                elapsed_ms=_elapsed(started),
                counts={"final_candidates": merged.count_final},
            )
        )

        preliminary = decide_preliminary(spec, plan, merged)
        trace.append(
            TraceEvent(
                stage="DECIDE",
                detail=preliminary.state.value,
                elapsed_ms=_elapsed(started),
            )
        )
        result = AgentRunResult(
            query_id=plan.query_id,
            spec=spec,
            execution_plan=plan,
            merged_result=merged,
            sql_result=sql_result,
            relation_result=relation_result,
            document_result=document_result,
            preliminary_decision=preliminary,
            evidence_requirements=list(plan.required_evidence_fields),
            trace_events=trace,
        )
        self._retrieval_cache.put(cache_key, result)
        return result


def _candidate_count(
    kind: RetrieverKind,
    sql_result: RetrievalResult | None,
    relation_result: RetrievalResult | None,
    document_result: RetrievalResult | None,
) -> int:
    if kind == RetrieverKind.SQL and sql_result is not None:
        return sql_result.count_final
    if kind == RetrieverKind.RELATION and relation_result is not None:
        return len(relation_result.relation_evidences)
    if kind == RetrieverKind.DOCUMENT and document_result is not None:
        return len(document_result.document_evidences)
    return 0


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def uuid4_fallback(spec: QuerySpec) -> str:
    from app.agent.execution_plan import compute_spec_hash

    return compute_spec_hash(spec)[:32]


def _dedupe_reason_codes(codes: list[ReasonCode]) -> list[ReasonCode]:
    seen: set[ReasonCode] = set()
    ordered: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered
