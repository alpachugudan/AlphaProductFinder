from __future__ import annotations

import pytest
from app.agent.decision import DecisionState
from app.agent.execution_plan import RetrieverKind
from app.agent.orchestrator import AgentOrchestrator
from app.core.errors import RetrieverFailure
from app.llm.mock_provider import MockLlmProvider
from app.query.enums import Intent, ProductFamily
from app.query.models import QuerySpec
from app.retrieval.models import Candidate, RetrievalContext, RetrievalResult


class StubSqlRetriever:
    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        return RetrievalResult(
            spec=spec,
            product_families=list(spec.product_families),
            batches=[],
            candidates=[
                Candidate(
                    product_uid="ETF_KR:001",
                    product_family=ProductFamily.ETF_KR,
                    source_table="PREF01N001",
                    source_key="1",
                    product_name="Test ETF",
                )
            ],
            count_before_filter=1,
            count_after_filter=1,
            count_after_quality=1,
            count_final=1,
            applied_filters=[],
            applied_sorts=[],
            exclusions=[],
            warnings=[],
            elapsed_ms=1,
        )


class FailingSqlRetriever:
    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        msg = "db down"
        raise RuntimeError(msg)


class CountingSqlRetriever(StubSqlRetriever):
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, spec: QuerySpec, context: RetrievalContext) -> RetrievalResult:
        self.calls += 1
        return await super().retrieve(spec, context)


class CountingMockLlmProvider(MockLlmProvider):
    def __init__(self) -> None:
        super().__init__()
        self.parse_calls = 0

    async def parse_query(self, question: str) -> QuerySpec:
        self.parse_calls += 1
        return await super().parse_query(question)


@pytest.mark.asyncio(loop_scope="module")
async def test_orchestrator_runs_filter_plan_with_mock_sql() -> None:
    orchestrator = AgentOrchestrator(sql_retriever=StubSqlRetriever())
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "investment_region", "operator": "CONTAINS", "value": "미국"}],
    )
    context = RetrievalContext(
        dataset_version_id=1,
        dataset_version_label="2026-07-11-baseline",
        session=object(),  # stub sql retriever ignores session
    )
    result = await orchestrator.run_with_spec(spec, context)
    assert result.execution_plan is not None
    assert {item.kind for item in result.execution_plan.retrievers} == {RetrieverKind.SQL}
    assert result.preliminary_decision.state == DecisionState.PRE_ANSWER
    assert result.preliminary_decision.selected_candidate_ids == ["ETF_KR:001"]
    assert any(event.stage == "DECIDE" for event in result.trace_events)


@pytest.mark.asyncio(loop_scope="module")
async def test_required_retriever_failure_raises_system_error() -> None:
    orchestrator = AgentOrchestrator(sql_retriever=FailingSqlRetriever())
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "investment_region", "operator": "CONTAINS", "value": "미국"}],
    )
    context = RetrievalContext(
        dataset_version_id=1,
        dataset_version_label="2026-07-11-baseline",
        session=object(),
    )
    with pytest.raises(RetrieverFailure):
        await orchestrator.run_with_spec(spec, context)


@pytest.mark.asyncio(loop_scope="module")
async def test_orchestrator_is_deterministic_with_same_spec() -> None:
    orchestrator = AgentOrchestrator(sql_retriever=StubSqlRetriever())
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "investment_region", "operator": "CONTAINS", "value": "미국"}],
    )
    context = RetrievalContext(
        dataset_version_id=1,
        dataset_version_label="2026-07-11-baseline",
        session=object(),
    )
    first = await orchestrator.run_with_spec(spec, context)
    second = await orchestrator.run_with_spec(spec, context)
    assert first.execution_plan is not None
    assert second.execution_plan is not None
    assert first.execution_plan.spec_hash == second.execution_plan.spec_hash
    assert first.preliminary_decision.state == second.preliminary_decision.state
    assert (
        first.preliminary_decision.selected_candidate_ids
        == second.preliminary_decision.selected_candidate_ids
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_orchestrator_cache_uses_versioned_queryspec_and_retrieval_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CountingMockLlmProvider()
    retriever = CountingSqlRetriever()
    monkeypatch.setattr("app.agent.orchestrator.get_llm_provider", lambda *_: provider)
    orchestrator = AgentOrchestrator(sql_retriever=retriever)
    context = RetrievalContext(
        dataset_version_id=1,
        dataset_version_label="2026-07-11-baseline",
        session=object(),
        external_version="external-a",
    )

    await orchestrator.run_with_question("미국 투자 국내 ETF 보수 낮은 순", context)
    await orchestrator.run_with_question("미국 투자 국내 ETF 보수 낮은 순", context)
    changed_external_context = RetrievalContext(
        dataset_version_id=1,
        dataset_version_label="2026-07-11-baseline",
        session=object(),
        external_version="external-b",
    )
    await orchestrator.run_with_question(
        "미국 투자 국내 ETF 보수 낮은 순", changed_external_context
    )

    assert provider.parse_calls == 1
    assert retriever.calls == 2
