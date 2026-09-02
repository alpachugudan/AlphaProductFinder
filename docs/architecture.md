# Product Finder 아키텍처

```text
question
  → QuerySpec (Mock 또는 HCX Structured Outputs)
  → allowlisted validation·policy
  → SQL Curated / frozen Relation / Document retrieval
  → deterministic merge·ranking
  → Curated 행·공식 문서 Evidence 역검증
  → ANSWER | ASK | ABSTAIN Guard
  → five-string GET /answer response
```

LLM은 QuerySpec 파싱과 최종 문장 생성에만 사용한다. 필터·정렬·집계·후보 결정·근거 선택은 결정적 코드가 수행한다.

데이터 적재는 Step 02/03의 명시적 CLI에서만 한다. `/answer`, health, Golden, benchmark는 53,375행 Raw나 44,415행 Curated를 다시 적재/재구축하지 않고 이미 활성화된 버전을 조회한다. QuerySpec cache와 retrieval cache는 dataset/external 버전 키를 포함하고 bounded capacity로 동작한다.

관계 검색은 외부 ticker UID를 Curated product UID에 결합한 후 관계 근거와 상품 원천을 분리 검증한다. 이 때문에 SQL의 선착순 top-N에서 관계 후보가 누락되는 문제가 재발하지 않는다.
