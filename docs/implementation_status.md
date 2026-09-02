# 구현 상태 추적

> 갱신 규칙: 각 Step 시작 시 `IN_PROGRESS`, 검증 PASS 후 `DONE`. 산출물·테스트 근거 없이 DONE 표시 금지

| Step | 상태 | 최근 갱신일 | 실제 완료 내용 | 검증 명령과 결과 | 보류·위험 |
|:---:|---|---|---|---|---|
| 01 프로젝트 골격과 개발환경 | DONE | 2026-09-02 | FastAPI 골격, Settings, health, pytest | pytest/ruff/mypy PASS | Python 3.12 미설치 — 3.11.2 검증 |
| 02 데이터셋 검증과 Raw 적재 | DONE | 2026-09-02 | manifest, validator, ingestion, Alembic, raw 4테이블, CLI | validate 53375행 OK, unit 27 + integration 4 PASS, ruff/mypy PASS | Python 3.12 미설치 — 3.11.2 검증 |
| 03 Curated Search 모델과 품질정책 | DONE | 2026-09-02 | curated 4테이블, metric/quality, search view, build/validate CLI | curated 44415행 OK, unit 38 + integration 10 PASS, ruff/mypy PASS | Python 3.12 미설치 — 3.11.2 검증 |
| 04 온톨로지와 QuerySpec | DONE | 2026-09-02 | TTL 5종, field_registry 32필드, QuerySpec, MockLlm | validate_ontology OK, unit+contract 23 PASS, ruff/mypy PASS | — |
| 05 SQL Retriever와 순위정책 | DONE | 2026-09-02 | SqlRetriever, filter_compiler, ranking, federated_merger, ProductRepository, benchmark CLI | unit 3 + integration 3 PASS, ruff/mypy PASS | — |
| 06 외부지식과 Relation Vector Retriever | DONE | 2026-09-02 | external 7테이블, snapshot ingest, Relation/Document retriever, coverage CLI | unit 1 + integration 6 PASS, network-zero PASS, ruff/mypy PASS | NCP embedding은 Step 10 |
| 07 Policy Engine과 Agent 오케스트레이션 | DONE | 2026-09-02 | orchestrator, policy_engine, merger, ANSWER/ASK/ABSTAIN/PRE_ANSWER | unit 16 PASS, ruff/mypy PASS | Evidence 최종 확정은 Step 08 |
| 08 Evidence와 답변생성 관측성 | DONE | 2026-09-02 | evidence manager/builder/serializer, answer_guard, think_trace, AgentAnswerService, mock generate_answer, audit migration 004 | unit 16 + integration 1 PASS, full unit 92 PASS, ruff/mypy PASS | Step 09 API 계약 연동 예정 |
| 09 평가 API 계약과 장애처리 | DONE | 2026-09-02 | `GET /answer` 5-string 고정 계약, 200 ASK/ABSTAIN·503 system mapping, input normalization, request deadline/cancellation, versioned QuerySpec·retrieval cache, live/ready, smoke CLI | unit+contract 108 PASS, ruff/mypy PASS, 실제 Mock endpoint smoke 200·2.743초, readiness OK | HCX 실제 provider/평가 모드 차단은 Step 10 |
| 10 HyperCLOVA X 실연동 | DONE | 2026-09-02 | HCX v3 provider, credit-only 호출 차단, Structured Outputs/answer wire, evaluation gate 구현 | Mock unit+contract 116 PASS, 실제 QuerySpec·ABSTAIN answer·evaluation startup·evaluation `/answer` E2E PASS | NCP Embedding v2는 P0 비필수·비활성 상태로 Step 06 lexical/relation 경로 유지 |
| 11 Golden E2E 성능 하드닝 | DONE | 2026-09-02 | Golden 50, 관계 ticker→ISIN 근거 결합, 0/sentinel rank 방어, Mock benchmark/release gate, 운영 문서 | Golden 50/50 PASS, warm p50 146ms/p95 1,595ms, release gate PASS, ruff/mypy PASS, 환경 격리 contract regression PASS | 실제 HCX 재호출은 Step 10의 사용자 승인 1회 E2E 증적을 재사용; 반복 실연동은 별도 승인 필요 |
| 12 NCP 배포와 제출 런북 | NOT_STARTED | — | — | — | — |

## Step 02 검증 기록

```text
python -m scripts.validate_source_hashes --manifest data/manifests/source_manifest.json
→ Validation OK, TOTAL 53375

python -m pytest tests/unit -q
→ 27 passed (~6min, 전수 Excel 검증 포함)

python -m ruff check .
→ All checks passed

python -m mypy app scripts
→ Success (22 files)

python -m pytest tests/integration -q
→ 4 passed (~7min, 전수 Excel 적재 2회 포함)

python -m pytest tests/unit tests/integration -q
→ 44 passed (~19min)
```

## Step 03 검증 기록

```text
alembic upgrade head
→ revision 002_curated_layer

python -m scripts.build_curated --dataset-version 2026-07-11-baseline
→ 21882 / 1780 / 6037 / 14716 (사모 8960 제외)

python -m scripts.validate_curated --dataset-version 2026-07-11-baseline
→ Curated validation OK

python -m pytest tests/unit/test_curated_quality.py tests/unit/test_curated_mappers.py -q
→ 7 passed

python -m pytest tests/integration/test_curation.py -q
→ 6 passed (~11min)

python -m pytest tests/unit tests/integration -q
→ 44 passed (~19min)
```

## Step 04 검증 기록

```text
python -m scripts.validate_ontology
→ ttl_files 5, field_count 32, synonym_concepts 14

python -m pytest tests/unit/test_queryspec_models.py tests/unit/test_queryspec_validator.py tests/unit/test_ontology_grounding.py tests/unit/test_mock_llm.py tests/contract -q
→ 23 passed

python -m pytest tests/unit tests/integration tests/contract -q
→ 67 passed (~18min)

python -m ruff check .
python -m mypy app scripts
→ PASS (43 files)
```

## Step 05 검증 기록

```text
python -m pytest tests/unit/test_retrieval_ranking.py -q
→ 3 passed

python -m pytest tests/integration/test_retrieval.py -q
→ 3 passed

python -m scripts.benchmark_retrieval --dataset-version 2026-07-11-baseline
→ latency sample OK
```

## Step 06 검증 기록

```text
alembic upgrade head
→ revision 003_external_knowledge

python -m scripts.ingest_external --manifest data/external/manifests/external_manifest.yaml
→ source 2 / entity 3 / alias 2 / holding 2 / relation 1 / chunk 2

python -m scripts.report_external_coverage
→ P0 target coverage JSON OK

python -m pytest tests/unit/test_external_resolution.py tests/integration/test_external.py -q
→ 7 passed

python -m ruff check .
python -m mypy app scripts
→ PASS
```

## Step 08 검증 기록

```text
alembic upgrade head
→ revision 004_audit_logs

python -m pytest tests/unit/test_evidence_*.py tests/unit/test_agent_policy.py -q
→ 23 passed

python -m pytest tests/integration/test_evidence_audit.py -q
→ 1 passed

python -m pytest tests/unit -q
→ 92 passed

python -m ruff check app/evidence app/agent app/llm/mock_provider.py
python -m mypy app/evidence app/agent app/llm/mock_provider.py
→ PASS
```

## Step 09 검증 기록

```text
alembic upgrade head
python -m scripts.ingest_excel --manifest data/manifests/source_manifest.json
python -m scripts.build_curated --dataset-version 2026-07-11-baseline
python -m scripts.ingest_external --manifest data/external/manifests/external_manifest.yaml
→ active dataset 2026-07-11-baseline, Raw 53,375, Curated 44,415, external snapshot ingest OK

python -m pytest tests/unit tests/contract -q
→ 108 passed (96 unit + 12 contract)

python -m ruff check .
python -m mypy app scripts
→ All checks passed / Success (87 source files)

python -m scripts.smoke_test_endpoint --base-url http://127.0.0.1:8000 --question-id Q-001 --question "잔존일수 365일 이하 채권"
→ PASS status=200 elapsed_seconds=2.743, exact five keys/string/echo assertion

Mock endpoint representative cases
→ ETF_KR ABSTAIN 200 / BOND_KR ABSTAIN 200 / ETF_GLOBAL ANSWER 200 / FUND_PUBLIC ABSTAIN 200
→ missing question ASK 200 / encoded special question ABSTAIN 200 / POST /answer 405

GET /health/ready
→ database, migration, dataset, ontology_registry, llm_provider all ok
```

## Step 10 중간 검증 기록 (실호출 전)

```text
$env:LLM_PROVIDER='mock'; python -m ruff check app tests
→ All checks passed

$env:LLM_PROVIDER='mock'; python -m mypy app scripts
→ Success: no issues found in 91 source files

$env:LLM_PROVIDER='mock'; python -m pytest tests/unit tests/contract -q
→ 115 passed in 161.99s

HCX HTTP mock 검증
→ v3 URI/header/usage parsing, 429 1회 재시도, 401 재시도 금지,
  Structured Outputs correction 1회, credit_only 미확인 시 HTTP 전 차단 PASS

실제 설정의 비밀 비노출 점검
→ provider=hyperclova, api_key_configured=true, models=HCX-007,
  billing_mode=credit_only, credit_balance_confirmed=false
→ 실제 NCP HTTP 호출 0회
```

## Step 10 실제 HCX smoke 기록

```text
사전 조건
→ HCX_API_KEY 존재, LLM_PROVIDER=hyperclova, HCX-007, credit_only 확인값=true
→ API key·프롬프트·answer 원문은 출력·저장하지 않음

HCX-007 Structured Outputs
→ HTTP 200 / NCP status 20000 / QuerySpec 재검증 PASS
→ question=향후 수익률을 예측해줘
→ intent=UNSUPPORTED_PREDICTION, families=0, filters=0, metrics=0
→ responseFormat은 thinking.effort=none(추론 비활성)에서만 성공 확인
→ thinking low/medium/high 및 Function Calling 결합은 계속 금지

HCX-007 final answer + Answer Guard
→ ABSTAIN prefix와 Answer Guard PASS
→ 초기에 잘못된 state prefix를 관측하여 STATE_PREFIX_MISMATCH guard와 1회 재생성 경로 추가

evaluation startup capability smoke
→ intent: 1,047 prompt + 58 completion tokens, 2.734s, HTTP 200
→ answer: 113 prompt + 20 completion tokens, 0.577s, HTTP 200
→ readiness probe 자체는 생성 호출을 반복하지 않음

evaluation GET /answer E2E (사용자 명시적 데이터 전송 승인 후 1회)
→ question_id=HCX-E2E-001, question=해외 ETF 순자산 1000억 이상
→ status=200, elapsed_seconds=6.845
→ five-string keys=answer,question,question_id,retrieved_context,think_trace PASS
→ 반환 원문과 전송된 금융 evidence는 로그·문서에 기록하지 않음
→ 테스트 Uvicorn PID 37904 종료, port 8001 listener=false 확인

최종 회귀
→ python -m pytest tests/unit tests/contract -q
→ 116 passed in 345.18s
```


## Step 07 검증 기록

```text
python -m pytest tests/unit/test_agent_routing.py tests/unit/test_agent_policy.py tests/unit/test_agent_merger.py tests/unit/test_agent_orchestrator.py -q
→ 16 passed

python -m ruff check app/agent tests/unit/test_agent_*.py
python -m mypy app/agent
→ PASS
```

## Step 11 검증 기록

```text
python -m scripts.run_golden --provider mock
→ 50/50 PASS
→ 외부 API 0회, 활성 Curated/동결 external snapshot만 사용

python -m scripts.run_benchmark --runs 1
→ cold 50 / warm 50 samples
→ warm p50=146ms, p95=1,595ms, max=4,496ms

python -m scripts.check_release_gate \
  --golden-report artifacts/golden/golden-20260902-231256.json \
  --benchmark-report artifacts/benchmark/benchmark-20260902-231711.json
→ PASS

python -m ruff check .
python -m mypy app scripts
→ PASS (96 source files)

환경 격리 회귀
→ .env의 LLM_PROVIDER=hyperclova가 test 설정에 섞이지 않도록
  contract는 llm_provider=mock을 명시하고, 기본값 테스트는 .env를 제외
→ deadline cancellation / settings default PASS
```
