# 데이터·근거 정책

## 버전과 범위

- Raw: 53,375행, 원본 Excel 변경 금지
- Curated Search Layer: 44,415행 (국내채권·국내 ETF·해외 ETF·공모펀드)
- 활성 데이터셋: `2026-07-11-baseline`
- 외부 지식: 네트워크 재수집 없이 manifest hash로 식별되는 동결 snapshot만 사용

## 값의 의미

- `null`/빈값, 숫자 `0`, sentinel date는 같은 값이 아니다.
- 순위에 쓰는 metric은 결측·`INVALID_FOR_DECISION` 값을 제외한다.
- 0/sentinel만 남은 후보는 `QUALITY_BLOCKED`로 답변하지 않는다.
- 공모펀드만 Curated 대상이다. 사모펀드는 검색 후보에 편입하지 않는다.
- `buyable_quantity`는 매수 가능성·재고 근거가 아니며 QuerySpec allowlist와 답변 근거에서 차단한다.

## 외부 관계 근거

보유종목 snapshot의 국내 ETF ticker는 Curated ETF의 ISIN UID로 해석한 뒤, 상품 원천 행과 공식 source document를 각각 검증한다. 즉 외부 `product_holding` 행 자체를 상품 데이터 근거로 사용하지 않는다.

## 전송과 로그

Mock Golden·benchmark·release gate는 외부 API를 호출하지 않는다. HCX에 보낼 수 있는 데이터는 사용자가 명시적으로 허용한 최소 질의와 근거뿐이며, API key·prompt·answer 원문·금융 evidence 원문은 보고서에 기록하지 않는다.
