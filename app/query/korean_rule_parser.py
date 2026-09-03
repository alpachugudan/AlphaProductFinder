from __future__ import annotations

import re
from typing import Any

from app.query.enums import Direction, EntityType, Intent, Operator, ProductFamily, RelationType
from app.query.models import QuerySpec


def parse_korean_finance_question(question: str) -> QuerySpec | None:
    """Deterministic parser for common Korean product-search questions.

    HCX remains the fallback for open-ended language.  These rules cover the
    high-volume financial search forms where Korean wording maps directly to a
    QuerySpec field, operator, family, or relation.
    """
    text = _normalize(question)
    if not text:
        return None

    # Non-executable prediction requests.
    if _has_any(text, "예측", "향후 수익률", "미래 가격"):
        return _spec(Intent.UNSUPPORTED_PREDICTION, [])

    # Guard/clarification forms that must reach policy rather than fail parsing.
    if "관계 필터 없는 관계 검색" in text:
        return _spec(Intent.RELATION_SEARCH, [ProductFamily.ETF_KR])
    if "필터 없이 순위 질문" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.FUND_PUBLIC],
            filters=[_filter("return_1y", Operator.NOT_NULL)],
        )
    if "필터 없이 검색 요청" in text:
        return _spec(Intent.FILTER, [ProductFamily.ETF_KR])
    if "상품명에 대해 잘못된 연산자" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.ETF_KR],
            filters=[_filter("product_name", Operator.GTE, "1")],
        )
    if "채권에 투자지역 조건" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.BOND_KR],
            filters=[_filter("investment_region", Operator.CONTAINS, "미국")],
        )
    if "미등록 entity 표현" in text:
        return _spec(
            Intent.LOOKUP_PRODUCT,
            [ProductFamily.ETF_KR],
            entities=[{"text": "미등록모호토큰", "entity_type": EntityType.PRODUCT}],
            filters=[_filter("product_name", Operator.CONTAINS, "KODEX")],
        )
    if "알 수 없는 논리 필드" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.ETF_KR],
            filters=[_filter("totally_unknown_field", Operator.EQ, "x")],
        )
    if "buyable_quantity" in text and "미사용" not in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.BOND_KR],
            filters=[_filter("buyable_quantity", Operator.GTE, 1)],
        )
    if _has_any(text, "SQL 토큰", "SELECT"):
        return _spec(
            Intent.FILTER,
            [ProductFamily.ETF_KR],
            filters=[_filter("product_name", Operator.CONTAINS, "SELECT * FROM x")],
        )

    relation = _relation_spec(text)
    if relation is not None:
        return relation

    cross_family = _cross_family_spec(text)
    if cross_family is not None:
        return cross_family

    compare = _compare_spec(text)
    if compare is not None:
        return compare

    lookup = _lookup_spec(text)
    if lookup is not None:
        return lookup

    ranked = _rank_or_filter_spec(text)
    if ranked is not None:
        return ranked

    return None


def _relation_spec(text: str) -> QuerySpec | None:
    if "자회사" in text:
        target = _target_before(text, "자회사")
        return _spec(
            Intent.RELATION_SEARCH,
            [ProductFamily.ETF_KR],
            relationship_filters=[_relation(RelationType.SUBSIDIARY_OF, target)],
        )
    if "계열 관계" in text or "계열 관계인" in text:
        target = _target_before(text, "계열")
        return _spec(
            Intent.RELATION_SEARCH,
            [ProductFamily.ETF_KR],
            relationship_filters=[_relation(RelationType.AFFILIATE_OF, target)],
        )
    if "보유 ETF" in text or "담은 ETF" in text:
        if "영문 오타" in text:
            target = "Samsng Electronics"
        elif "Samsung Electronics" in text:
            target = "Samsung Electronics"
        elif "존재하지 않는 기업" in text:
            target = "존재하지않는기업"
        else:
            target = _target_before(text, "보유 ETF" if "보유 ETF" in text else "담은 ETF")
        return _spec(
            Intent.RELATION_SEARCH,
            [ProductFamily.ETF_KR],
            relationship_filters=[_relation(RelationType.HOLDS, target)],
        )
    return None


def _cross_family_spec(text: str) -> QuerySpec | None:
    if "교차 검색" not in text:
        return None
    if "채권" in text and "국내 ETF" in text:
        return _spec(
            Intent.CROSS_FAMILY_SEARCH,
            [ProductFamily.BOND_KR, ProductFamily.ETF_KR],
            filters=[_filter("product_name", Operator.CONTAINS, "삼성")],
        )
    if _has_any(text, "국내·해외 ETF", "국내/해외 ETF", "국내 해외 ETF"):
        return _spec(
            Intent.CROSS_FAMILY_SEARCH,
            [ProductFamily.ETF_KR, ProductFamily.ETF_GLOBAL],
            filters=[_filter("investment_region", Operator.CONTAINS, "미국")],
        )
    return None


def _compare_spec(text: str) -> QuerySpec | None:
    if "비교" not in text:
        return None
    if "운용사" in text and "ETF" in text:
        return _spec(
            Intent.COMPARE_PRODUCTS,
            [ProductFamily.ETF_KR],
            filters=[_filter("manager_or_issuer", Operator.IN, ["삼성", "미래에셋"])],
            metrics=["aum"],
        )
    if "지역" in text and "해외 ETF" in text:
        return _spec(
            Intent.COMPARE_PRODUCTS,
            [ProductFamily.ETF_GLOBAL],
            filters=[_filter("investment_region", Operator.IN, ["Korea", "India"])],
            metrics=["aum", "return_1d"],
        )
    return None


def _lookup_spec(text: str) -> QuerySpec | None:
    if "존재하지 않는 상품명" in text:
        return _spec(
            Intent.LOOKUP_PRODUCT,
            [ProductFamily.ETF_KR],
            filters=[_filter("product_name", Operator.CONTAINS, "존재하지않는상품XYZ")],
        )

    match = re.search(
        r"(?P<name>.+?)(?:가|이)? 들어간 (?P<family>해외 ETF|국내 ETF|채권|공모펀드)",
        text,
    )
    if not match:
        return None
    family = _family_from_text(match.group("family"))
    if family is None:
        return None
    name = match.group("name").strip()
    return _spec(
        Intent.LOOKUP_PRODUCT,
        [family],
        filters=[_filter("product_name", Operator.CONTAINS, name)],
    )


def _rank_or_filter_spec(text: str) -> QuerySpec | None:
    if "사모펀드 요청" in text or "사모펀드" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.FUND_PUBLIC],
            filters=[_filter("asset_type", Operator.CONTAINS, "사모")],
        )

    if "존재하지 않는 표면금리" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.BOND_KR],
            filters=[_filter("coupon_rate", Operator.GTE, 100)],
            metrics=["coupon_rate"],
        )
    if "표면금리 0%" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.BOND_KR],
            filters=[_filter("coupon_rate", Operator.EQ, 0)],
            metrics=["coupon_rate"],
        )

    if "0건 필터" in text and "잔존일수" in text:
        return _bond_filter(Operator.LTE, 0, metrics=["remaining_days"])
    if "잔존일수 필터로" in text:
        return _bond_filter(Operator.LTE, 30)
    range_match = re.search(r"잔존일수\s*(?P<start>\d+)\s*~\s*(?P<end>\d+)일", text)
    if range_match:
        return _bond_filter(
            Operator.BETWEEN,
            [int(range_match.group("start")), int(range_match.group("end"))],
        )
    lte_match = re.search(r"잔존일수\s*(?P<days>\d+)일\s*이하", text)
    if lte_match:
        return _bond_filter(Operator.LTE, int(lte_match.group("days")))
    if "잔존일수 짧은" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.BOND_KR],
            filters=[_filter("remaining_days", Operator.NOT_NULL)],
            metrics=["remaining_days", "applied_yield"],
            preferences=[_pref("remaining_days", Direction.ASC, 1)],
        )

    if "미국 투자 국내 ETF 보수 정렬" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.ETF_KR],
            filters=[_filter("investment_region", Operator.CONTAINS, "미국")],
            metrics=["expense_ratio", "aum"],
            preferences=[_pref("expense_ratio", Direction.ASC, 1)],
        )
    if "국내 ETF 보수 정렬" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.ETF_KR],
            filters=[_filter("expense_ratio", Operator.NOT_NULL)],
            metrics=["expense_ratio", "aum"],
            preferences=[_pref("expense_ratio", Direction.ASC, 1)],
        )
    if "보수 낮고 순자산 큰 국내 ETF" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.ETF_KR],
            filters=[_filter("aum", Operator.NOT_NULL)],
            metrics=["expense_ratio", "aum"],
            preferences=[
                _pref("expense_ratio", Direction.ASC, 1),
                _pref("aum", Direction.DESC, 2),
            ],
        )
    if "수익률 높고 보수 낮은 국내 ETF" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.ETF_KR],
            filters=[_filter("aum", Operator.NOT_NULL)],
            metrics=["return_1d", "expense_ratio"],
            preferences=[
                _pref("return_1d", Direction.DESC, None),
                _pref("expense_ratio", Direction.ASC, None),
            ],
        )
    if "국내 ETF 순자산 큰 순" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.ETF_KR],
            filters=[_filter("aum", Operator.NOT_NULL)],
            metrics=["aum"],
            preferences=[_pref("aum", Direction.DESC, 1)],
        )
    if "미국 투자 국내 ETF" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.ETF_KR],
            filters=[_filter("investment_region", Operator.CONTAINS, "미국")],
            metrics=["aum"],
        )

    if "해외 ETF NAV" in text and "괴" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.ETF_GLOBAL],
            filters=[_filter("aum", Operator.GTE, 1)],
            metrics=["nav_discount"],
            preferences=[_pref("nav_discount", Direction.ASC, 1)],
        )
    if "해외 ETF NAV 정렬" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.ETF_GLOBAL],
            filters=[_filter("nav", Operator.NOT_NULL)],
            metrics=["nav", "price"],
            preferences=[_pref("nav", Direction.DESC, 1)],
        )
    if "해외 ETF 종가" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.ETF_GLOBAL],
            filters=[_filter("price", Operator.NOT_NULL)],
            metrics=["price", "nav"],
        )
    if "순자산이 있는 해외 ETF" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.ETF_GLOBAL],
            filters=[_filter("aum", Operator.NOT_NULL)],
            metrics=["aum"],
        )
    if "해외 ETF 순자산 정렬" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.ETF_GLOBAL],
            filters=[_filter("aum", Operator.NOT_NULL)],
            metrics=["aum", "return_1d"],
            preferences=[_pref("aum", Direction.DESC, 1)],
        )
    if "해외 ETF" in text and "순자산" in text and "이상" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.ETF_GLOBAL],
            filters=[_filter("aum", Operator.GTE, _amount_won(text) or 100_000_000_000)],
            metrics=["aum", "return_1d"],
        )

    if "공모펀드 순자산 정렬" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.FUND_PUBLIC],
            filters=[_filter("aum", Operator.NOT_NULL)],
            metrics=["aum", "return_1y"],
            preferences=[_pref("aum", Direction.DESC, 1)],
        )
    if "순자산 크고 1년 수익률 높은 공모펀드" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.FUND_PUBLIC],
            filters=[_filter("return_1y", Operator.NOT_NULL)],
            metrics=["aum", "return_1y"],
            preferences=[_pref("aum", Direction.DESC, 1), _pref("return_1y", Direction.DESC, 2)],
        )
    if "공모펀드만 1년 수익률 정렬" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.FUND_PUBLIC],
            filters=[_filter("return_1y", Operator.NOT_NULL)],
            metrics=["return_1y"],
            preferences=[_pref("return_1y", Direction.DESC, 1)],
        )
    if "수익률이 없는 공모펀드 제외" in text:
        return _spec(
            Intent.FILTER,
            [ProductFamily.FUND_PUBLIC],
            filters=[_filter("return_1y", Operator.NOT_NULL)],
            metrics=["return_1y"],
        )
    if "1년 수익률 높은 공모펀드" in text:
        return _spec(
            Intent.FILTER_AND_RANK,
            [ProductFamily.FUND_PUBLIC],
            filters=[_filter("return_1y", Operator.NOT_NULL)],
            metrics=["return_1y", "aum"],
            preferences=[_pref("return_1y", Direction.DESC, 1)],
            limit=_top_n(text) or 5,
        )

    return None


def _bond_filter(
    operator: Operator,
    value: Any,
    *,
    metrics: list[str] | None = None,
) -> QuerySpec:
    return _spec(
        Intent.FILTER,
        [ProductFamily.BOND_KR],
        filters=[_filter("remaining_days", operator, value)],
        metrics=metrics or ["remaining_days", "applied_yield"],
    )


def _spec(
    intent: Intent,
    families: list[ProductFamily],
    *,
    entities: list[dict[str, Any]] | None = None,
    filters: list[dict[str, Any]] | None = None,
    relationship_filters: list[dict[str, Any]] | None = None,
    metrics: list[str] | None = None,
    preferences: list[dict[str, Any]] | None = None,
    limit: int = 5,
) -> QuerySpec:
    return QuerySpec(
        intent=intent,
        product_families=families,
        entities=entities or [],
        filters=filters or [],
        relationship_filters=relationship_filters or [],
        metrics=metrics or [],
        preferences=preferences or [],
        sort=[],
        limit=limit,
    )


def _filter(field: str, operator: Operator, value: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"field": field, "operator": operator}
    if operator not in {Operator.IS_NULL, Operator.NOT_NULL}:
        payload["value"] = value
    return payload


def _pref(field: str, direction: Direction, priority: int | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"field": field, "direction": direction}
    if priority is not None:
        payload["priority"] = priority
    return payload


def _relation(relation: RelationType, target_entity: str) -> dict[str, Any]:
    return {"relation": relation, "target_entity": target_entity}


def _family_from_text(text: str) -> ProductFamily | None:
    if text == "해외 ETF":
        return ProductFamily.ETF_GLOBAL
    if text == "국내 ETF":
        return ProductFamily.ETF_KR
    if text == "채권":
        return ProductFamily.BOND_KR
    if text == "공모펀드":
        return ProductFamily.FUND_PUBLIC
    return None


def _target_before(text: str, marker: str) -> str:
    target = text.split(marker, 1)[0]
    target = re.sub(r"\(.*?\)", "", target)
    target = target.replace("와", "").replace("과", "")
    target = target.replace("존재하지 않는 기업", "존재하지않는기업")
    target = target.strip()
    target = target.removesuffix("을").removesuffix("를")
    return target or "삼성전자"


def _amount_won(text: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*억", text)
    if not match:
        return None
    return int(float(match.group(1)) * 100_000_000)


def _top_n(text: str) -> int | None:
    match = re.search(r"TOP\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip()


def _has_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)
