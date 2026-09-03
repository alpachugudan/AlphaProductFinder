from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.decision import Decision, DecisionState
from app.agent.orchestrator import AgentOrchestrator, AgentRunResult, finalize_decision
from app.config.settings import Settings, get_settings
from app.evidence.answer_guard import FORBIDDEN_PHRASES, guard_answer
from app.evidence.audit import AuditWriter
from app.evidence.builder import build_evidence_bundles, build_relationship_evidence_items
from app.evidence.manager import EvidenceManager
from app.evidence.models import (
    AnswerContext,
    EvidenceBundle,
    EvidenceValidationResult,
    GuardResult,
    summarize_spec,
)
from app.evidence.serializer import serialize_retrieved_context
from app.evidence.think_trace import build_execution_trace, serialize_think_trace
from app.external.ingestion import MANIFEST_PATH, compute_manifest_hash
from app.external.models import ExternalIngestionRun, ExternalIngestionStatus
from app.llm.factory import get_llm_provider
from app.query.models import QuerySpec
from app.retrieval.models import RetrievalContext

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentAnswerResult:
    run: AgentRunResult
    final_decision: Decision
    retrieved_context: str
    think_trace: str
    answer_text: str
    guard_result: GuardResult
    evidence_hash: str


class AgentAnswerService:
    def __init__(
        self,
        *,
        orchestrator: AgentOrchestrator | None = None,
        evidence_manager: EvidenceManager | None = None,
        audit_writer: AuditWriter | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._orchestrator = orchestrator or AgentOrchestrator(settings=self._settings)
        self._evidence_manager = evidence_manager or EvidenceManager()
        self._audit_writer = audit_writer or AuditWriter()

    async def answer_question(self, question: str, context: RetrievalContext) -> AgentAnswerResult:
        started = time.perf_counter()
        run = await self._orchestrator.run_with_question(question, context)
        return await self._finalize(run, question=question, context=context, started=started)

    async def answer_with_spec(
        self, spec: QuerySpec, *, question: str, context: RetrievalContext
    ) -> AgentAnswerResult:
        """Golden/E2E용 결정적 QuerySpec으로 전체 답변 파이프라인을 직접 실행한다."""
        started = time.perf_counter()
        run = await self._orchestrator.run_with_spec(spec, context)
        return await self._finalize(run, question=question, context=context, started=started)

    async def _finalize(
        self,
        run: AgentRunResult,
        *,
        question: str,
        context: RetrievalContext,
        started: float,
    ) -> AgentAnswerResult:
        validation: EvidenceValidationResult | None = None
        bundles = []
        standalone_relations = []
        if run.merged_result is not None and run.preliminary_decision.selected_candidate_ids:
            bundles = build_evidence_bundles(
                run.merged_result,
                selected_product_uids=run.preliminary_decision.selected_candidate_ids,
            )
            validation = self._evidence_manager.validate(
                context.session,
                dataset_version_id=context.dataset_version_id,
                bundles=bundles,
            )
            final_decision = finalize_decision(run.preliminary_decision, validation)
            bundles = validation.bundles
        elif (
            run.merged_result is not None
            and run.preliminary_decision.state.value == "PRE_ANSWER"
            and run.spec.intent.value == "RELATION_SEARCH"
        ):
            standalone_relations = build_relationship_evidence_items(
                run.merged_result.relation_evidences
            )
            self._evidence_manager.validate_relationship_evidence(
                context.session, standalone_relations
            )
            final_decision = Decision(
                state=DecisionState.ANSWER,
                reason_codes=run.preliminary_decision.reason_codes,
                warnings=run.preliminary_decision.warnings,
                execution_summary={**run.preliminary_decision.execution_summary, "finalized": True},
            )
        else:
            final_decision = run.preliminary_decision

        retrieved_context = serialize_retrieved_context(
            bundles, relationship_evidence=standalone_relations
        )
        trace = build_execution_trace(
            run,
            dataset_version=context.dataset_version_label,
            external_manifest_hash=_external_manifest_hash(context.session),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            decision_state=final_decision.state.value,
            reason_codes=final_decision.reason_codes,
        )
        think_trace = serialize_think_trace(trace)

        answer_context = AnswerContext(
            question=question,
            spec_summary=summarize_spec(run.spec),
            decision=final_decision,
            evidence_bundles=bundles,
            retrieved_context=retrieved_context,
            relation_evidence=standalone_relations,
            forbidden_phrases=list(FORBIDDEN_PHRASES),
        )
        provider = get_llm_provider(self._settings)
        answer_text = await provider.generate_answer(answer_context)
        guard_result = guard_answer(
            answer_text,
            decision=final_decision,
            evidence_bundles=bundles,
            relation_evidence=standalone_relations,
        )
        if not guard_result.passed:
            answer_text = await provider.regenerate_answer(
                answer_context,
                guard_result.reason_codes,
            )
            guard_result = guard_answer(
                answer_text,
                decision=final_decision,
                evidence_bundles=bundles,
                relation_evidence=standalone_relations,
            )
            if not guard_result.passed:
                logger.warning(
                    "HCX answer guard failed twice; using deterministic safe fallback",
                    extra={"guard_reason_codes": guard_result.reason_codes},
                )
                answer_text = _safe_answer_fallback(final_decision)
                guard_result = guard_answer(
                    answer_text,
                    decision=final_decision,
                    evidence_bundles=bundles,
                    relation_evidence=standalone_relations,
                )

        evidence_hash = validation.evidence_hash if validation else ""
        self._safe_audit(
            context=context,
            run=run,
            question=question,
            final_decision=final_decision,
            bundles=bundles,
            evidence_hash=evidence_hash,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

        return AgentAnswerResult(
            run=run,
            final_decision=final_decision,
            retrieved_context=retrieved_context,
            think_trace=think_trace,
            answer_text=answer_text,
            guard_result=guard_result,
            evidence_hash=evidence_hash,
        )

    def _safe_audit(
        self,
        *,
        context: RetrievalContext,
        run: AgentRunResult,
        question: str,
        final_decision: Decision,
        bundles: list[EvidenceBundle],
        evidence_hash: str,
        elapsed_ms: int,
    ) -> None:
        try:
            self._audit_writer.write(
                context.session,
                request_id=run.query_id,
                question_hash=_hash_text(question),
                decision_state=final_decision.state.value,
                elapsed_ms=elapsed_ms,
                llm_call_count=1,
                query_hash=run.execution_plan.spec_hash if run.execution_plan else "",
                spec_summary=summarize_spec(run.spec),
                selected_retrievers=[
                    item.kind.value for item in run.execution_plan.retrievers
                ]
                if run.execution_plan
                else [],
                candidate_counts={
                    "final": run.merged_result.count_final if run.merged_result else 0
                },
                selected_source_keys=[bundle.source_key for bundle in bundles],
                evidence_hash=evidence_hash,
                model_name=self._settings.llm_provider,
                dataset_version=context.dataset_version_label,
                external_manifest_hash=_external_manifest_hash(context.session),
            )
        except Exception:
            logger.exception("audit log write failed")


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_answer_fallback(decision: Decision) -> str:
    """Availability fallback when two generated answers fail the safety guard."""
    if decision.state == DecisionState.ANSWER:
        return "ANSWER: 제공된 근거 데이터 기준의 조회 결과입니다."
    if decision.state == DecisionState.ASK:
        return "ASK: 조회 조건을 조금 더 구체적으로 알려주세요."
    return "ABSTAIN: 제공된 데이터와 근거 범위에서는 확인할 수 없습니다."


def _external_manifest_hash(session: Session) -> str | None:
    if not MANIFEST_PATH.exists():
        return None
    latest = session.scalar(
        select(ExternalIngestionRun.manifest_hash)
        .where(ExternalIngestionRun.status == ExternalIngestionStatus.SUCCESS.value)
        .order_by(ExternalIngestionRun.id.desc())
    )
    return latest or compute_manifest_hash(MANIFEST_PATH)
