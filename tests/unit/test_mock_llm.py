from __future__ import annotations

import pytest
from app.llm.mock_provider import MockLlmError, MockLlmProvider
from app.query.enums import ProductFamily


@pytest.mark.asyncio(loop_scope="module")
async def test_mock_provider_returns_same_spec_for_same_question() -> None:
    provider = MockLlmProvider()
    question = "미국 투자 국내 ETF 보수 낮은 순"
    first = await provider.parse_query(question)
    second = await provider.parse_query(question)
    assert first.model_dump() == second.model_dump()
    assert first.product_families == [ProductFamily.ETF_KR]


@pytest.mark.asyncio(loop_scope="module")
async def test_mock_provider_rejects_unknown_question() -> None:
    provider = MockLlmProvider()
    with pytest.raises(MockLlmError):
        await provider.parse_query("알 수 없는 질문")


@pytest.mark.asyncio(loop_scope="module")
async def test_mock_provider_covers_all_families() -> None:
    provider = MockLlmProvider()
    cases = {
        "미국 투자 국내 ETF 보수 낮은 순": ProductFamily.ETF_KR,
        "잔존일수 365일 이하 채권": ProductFamily.BOND_KR,
        "해외 ETF 순자산 1000억 이상": ProductFamily.ETF_GLOBAL,
        "1년 수익률 높은 공모펀드": ProductFamily.FUND_PUBLIC,
    }
    for question, family in cases.items():
        spec = await provider.parse_query(question)
        assert spec.product_families == [family]
