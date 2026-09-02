from __future__ import annotations

from app.agent.execution_plan import MergeMode
from app.agent.merger import merge_retrieval_results
from app.query.enums import Intent, ProductFamily
from app.query.models import QuerySpec
from app.retrieval.models import Candidate, RelationEvidence, RetrievalResult


def test_merge_deduplicates_candidates_by_product_uid() -> None:
    spec = QuerySpec(
        intent=Intent.FILTER,
        product_families=[ProductFamily.ETF_KR],
        filters=[{"field": "investment_region", "operator": "CONTAINS", "value": "미국"}],
    )
    sql_result = RetrievalResult(
        spec=spec,
        product_families=[ProductFamily.ETF_KR],
        batches=[],
        candidates=[
            Candidate(
                product_uid="ETF_KR:001",
                product_family=ProductFamily.ETF_KR,
                source_table="PREF01N001",
                source_key="1",
                product_name="A",
                selection_reasons=["SQL"],
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
    relation_result = RetrievalResult(
        spec=spec,
        product_families=[ProductFamily.ETF_KR],
        batches=[],
        candidates=[
            Candidate(
                product_uid="ETF_KR:001",
                product_family=ProductFamily.ETF_KR,
                source_table="product_holding",
                source_key="2",
                product_name="A",
                selection_reasons=["RELATION_HOLDS"],
            )
        ],
        count_before_filter=0,
        count_after_filter=0,
        count_after_quality=0,
        count_final=1,
        applied_filters=[],
        applied_sorts=[],
        exclusions=[],
        warnings=[],
        elapsed_ms=1,
        relation_evidences=[
            RelationEvidence(
                relation_type="HOLDS",
                subject_entity_id="ETF_KR:001",
                object_entity_id="ENT:1",
                source_document_id="doc-1",
                source_title="t",
                source_publisher="p",
                source_url=None,
                content_sha256="deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                product_uid="ETF_KR:001",
            )
        ],
    )
    merged = merge_retrieval_results(
        spec=spec,
        merge_mode=MergeMode.RELATION_INTERSECT,
        sql_result=sql_result,
        relation_result=relation_result,
        document_result=None,
    )
    assert len(merged.candidates) == 1
    assert "SQL" in merged.candidates[0].selection_reasons
    assert "RELATION_HOLDS" in merged.candidates[0].selection_reasons
    assert len(merged.relation_evidences) == 1
