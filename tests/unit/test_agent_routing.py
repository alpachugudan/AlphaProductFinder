from __future__ import annotations

from app.agent.execution_plan import RetrieverKind
from app.agent.policy_engine import select_retrievers
from app.query.enums import Intent, ProductFamily, RelationType
from app.query.models import QuerySpec, RelationshipFilterClause


def test_unsupported_prediction_selects_no_retriever() -> None:
    spec = QuerySpec(intent=Intent.UNSUPPORTED_PREDICTION, product_families=[ProductFamily.ETF_KR])
    assert select_retrievers(spec) == []


def test_filter_and_rank_selects_sql_only() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER_AND_RANK,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "investment_region", "operator": "CONTAINS", "value": "미국"}],
        preferences=[{"field": "expense_ratio", "direction": "ASC", "priority": 1}],
    )
    kinds = {item.kind for item in select_retrievers(spec)}
    assert kinds == {RetrieverKind.SQL}


def test_relation_filter_adds_relation_retriever() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "sale_status", "operator": "EQ", "value": "Y"}],
        relationship_filters=[
            RelationshipFilterClause(relation=RelationType.HOLDS, target_entity="삼성전자")
        ],
    )
    kinds = {item.kind for item in select_retrievers(spec)}
    assert RetrieverKind.SQL in kinds
    assert RetrieverKind.RELATION in kinds
    assert RetrieverKind.DOCUMENT not in kinds


def test_relation_search_selects_sql_relation_not_document_by_default() -> None:
    spec = QuerySpec(
        intent=Intent.RELATION_SEARCH,
        product_families=[ProductFamily.ETF_KR],
        relationship_filters=[
            RelationshipFilterClause(relation=RelationType.HOLDS, target_entity="삼성전자")
        ],
    )
    plans = select_retrievers(spec)
    kinds = {item.kind for item in plans}
    assert kinds == {RetrieverKind.SQL, RetrieverKind.RELATION}
    required = {item.kind for item in plans if item.required}
    assert required == {RetrieverKind.SQL, RetrieverKind.RELATION}


def test_explain_term_requires_document_retriever() -> None:
    spec = QuerySpec(
        intent=Intent.EXPLAIN_TERM,
        product_families=[ProductFamily.ETF_KR],
        entities=[{"text": "ETF", "entity_type": "THEME"}],
    )
    kinds = {item.kind for item in select_retrievers(spec)}
    assert RetrieverKind.DOCUMENT in kinds
