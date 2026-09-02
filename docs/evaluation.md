# Step 11 평가·Golden E2E 기준

## 목적과 범위

Golden suite는 50개의 버전 고정 `QuerySpec`을 입력으로 사용해 `validate → retrieve → merge → evidence → answer guard` 전체 경로를 검증한다. 결과 판정은 자연어의 문장 유사도가 아니라 의도·상품군·결정 상태·사유코드·후보 수·근거 hash·답변 prefix로 한다.

- 원본: `tests/golden/questions.yaml` (정확히 50개, `known_gap` 허용 안 함)
- Mock Golden: DB와 동결 external snapshot을 실제 사용하지만 LLM 호출은 0회
- HCX Golden: `--provider hyperclova --allow-billable-hcx`를 명시해야만 실행된다. CLOVA Studio 크레딧이 차감될 수 있으므로 별도 승인 없이는 실행하지 않는다.

## 실행

```powershell
python -m scripts.run_golden --provider mock
python -m scripts.run_benchmark --runs 1
python -m scripts.check_release_gate
```

보고서는 질문·답변·금융 근거 원문을 쓰지 않고, case ID·질문 SHA-256·상태·지연시간만 `artifacts/`에 남긴다.

## 통과 조건

1. Golden 50/50 PASS 및 남은 `known_gap` 0개
2. ANSWER는 선택 후보의 Curated 원천 행과 metric을 역검증하고, 관계 답변은 동결된 공식 문서를 역검증한다.
3. ASK/ABSTAIN은 후보 context를 노출하지 않는다.
4. `buyable_quantity`는 retrieved context/답변 근거에 들어갈 수 없다.
5. Mock warm E2E p50 ≤ 8초, p95 ≤ 20초

실제 HCX 경로는 Step 10에서 Structured Outputs·ABSTAIN Guard·evaluation startup smoke·`GET /answer` 1회 E2E를 이미 통과했다. Step 11은 같은 경로의 데이터·근거·정책 회귀를 비용 없는 Mock Golden으로 반복 검증한다. 새로운 금융 evidence 전송 또는 반복 HCX benchmark는 별도 사용자 승인이 필요하다.
