from __future__ import annotations

from app.golden.runner import load_golden_cases
from app.query.korean_rule_parser import parse_korean_finance_question


def test_rule_parser_covers_release_golden_intent_and_families() -> None:
    for case in load_golden_cases():
        spec = parse_korean_finance_question(case.question)
        assert spec is not None, case.case_id
        assert spec.intent == case.spec.intent, case.case_id
        assert spec.product_families == case.spec.product_families, case.case_id


def test_rule_parser_maps_representative_filters_and_relations() -> None:
    spec = parse_korean_finance_question("해외 ETF 중 순자산 1000억 이상")
    assert spec is not None
    assert spec.filters[0].field == "aum"
    assert spec.filters[0].operator.value == "GTE"
    assert spec.filters[0].value == 100_000_000_000

    spec = parse_korean_finance_question("삼성전자를 담은 ETF")
    assert spec is not None
    assert spec.relationship_filters[0].relation.value == "HOLDS"
    assert spec.relationship_filters[0].target_entity == "삼성전자"

    spec = parse_korean_finance_question("미등록 entity 표현 (grounding 확인 요청)")
    assert spec is not None
    assert spec.entities[0].text == "미등록모호토큰"
    assert spec.filters[0].value == "KODEX"
