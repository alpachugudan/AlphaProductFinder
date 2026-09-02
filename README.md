# Product Finder — 금융상품 Agent

미래에셋 AI Festival 과제용 백엔드. 4종 금융상품 마스터(국내채권·국내 ETF·해외 ETF·공모펀드)를 기반으로 자연어 질의에 조회·비교·설명을 제공하는 Agent RAG/QA 시스템

**현재 완료 단계:** Step 11 — Golden E2E·성능 하드닝  
**다음 단계:** Step 12 — NCP 배포·제출 런북

> Step 10 완료: HCX-007 Structured Outputs QuerySpec, 최종 ANSWER/ASK/ABSTAIN 생성 Guard, evaluation 기동 smoke, 실제 evaluation `/answer` E2E를 검증했습니다. NCP Embedding v2는 P0 경로에서 비활성입니다.

> Step 11 완료: 동결 데이터 기준 Mock Golden 50/50, cold/warm 100개 성능 샘플, release gate를 통과했습니다. 이 단계에서는 CLOVA Studio 호출을 하지 않았으며 Step 10의 1회 실제 HCX E2E 증적을 재사용했습니다.

---

## 요구 환경

- Python **3.11+** (설계 목표 3.12, 현재 개발 환경 3.11.2 검증)
- PostgreSQL 16 + **pgvector** (개발용 Docker Compose 제공)
- Windows PowerShell / Linux 컨테이너

---

## 로컬 설치

```powershell
cd resource
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```

---

## PostgreSQL 기동 (개발)

```powershell
cd deploy
docker compose -f docker-compose.dev.yml up -d
cd ..
alembic upgrade head
```

---

## 데이터 검증 · Raw 적재

```powershell
python -m scripts.validate_source_hashes --manifest data/manifests/source_manifest.json
python -m scripts.ingest_excel --manifest data/manifests/source_manifest.json
```

기대 Raw 건수:

| 테이블 | 건수 |
|--------|-----:|
| raw_bond_kr | 21,882 |
| raw_etf_kr | 1,780 |
| raw_etf_global | 6,037 |
| raw_fund | 23,676 |
| **합계(Raw)** | **53,375** |

Curated 건수(공모펀드만 Search Layer):

| 테이블 | 건수 |
|--------|-----:|
| product_bond_kr | 21,882 |
| product_etf_kr | 1,780 |
| product_etf_global | 6,037 |
| product_fund_public | 14,716 |
| **합계(Curated)** | **44,415** |

---

## Curated 빌드 · 검증

```powershell
python -m scripts.build_curated --dataset-version 2026-07-11-baseline
python -m scripts.validate_curated --dataset-version 2026-07-11-baseline
```

---

## Ontology · QuerySpec

```powershell
python -m scripts.validate_ontology
python -m pytest tests/unit/test_queryspec_models.py tests/unit/test_queryspec_validator.py tests/contract -q
```

## Structured Retrieval (Step 05)

```powershell
python -m scripts.benchmark_retrieval --dataset-version 2026-07-11-baseline
python -m pytest tests/unit/test_retrieval_ranking.py tests/integration/test_retrieval.py -q
```

## External Knowledge (Step 06)

평가 경로는 동결 snapshot만 사용하며 network call 0회

```powershell
python -m scripts.collect_external --targets data/external/targets.yaml
python -m scripts.normalize_external --manifest data/external/manifests/external_manifest.yaml
python -m scripts.ingest_external --manifest data/external/manifests/external_manifest.yaml
python -m scripts.report_external_coverage
python -m pytest tests/unit/test_external_resolution.py tests/integration/test_external.py -q
```

P0 target 중 공식 자료 미공개 항목은 `coverage_status=NOT_AVAILABLE_FROM_OFFICIAL_SOURCE`로 기록

## Agent · Policy Engine (Step 07)

```powershell
python -m pytest tests/unit/test_agent_routing.py tests/unit/test_agent_policy.py tests/unit/test_agent_merger.py tests/unit/test_agent_orchestrator.py -q
```

- `AgentOrchestrator`: validate → plan → retrieve → merge → PRE_ANSWER/ASK/ABSTAIN
- `finalize_decision()`: Evidence 검증 후 ANSWER 확정

## Evidence · Answer · Audit (Step 08)

```powershell
python -m pytest tests/unit/test_evidence_*.py tests/integration/test_evidence_audit.py -q
```

- `EvidenceManager`: Curated row·metric·source document 역검증
- `serialize_retrieved_context()`: 결정적 `retrieved_context` 문자열
- `AgentAnswerService`: evidence → mock answer → guard → audit log
- Alembic `004_audit_logs`: `request_log`, `execution_log`


## FastAPI 기동

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health 확인:

```powershell
curl http://localhost:8000/health/live
```

## 평가 API 계약 (Step 09)

평가기 호출은 인증 없이 **GET** `/answer`만 사용합니다. 응답은 아래 순서의 다섯 문자열 필드만 반환합니다.

```powershell
curl.exe --noproxy "*" -sG `
  --data-urlencode "question_id=Q-001" `
  --data-urlencode "question=해외 ETF 순자산 1000억 이상" `
  http://127.0.0.1:8000/answer

python -m scripts.smoke_test_endpoint `
  --base-url http://127.0.0.1:8000 `
  --question-id Q-001 `
  --question "해외 ETF 순자산 1000억 이상"
```

```json
{
  "question_id": "Q-001",
  "question": "해외 ETF 순자산 1000억 이상",
  "retrieved_context": "...",
  "think_trace": "...",
  "answer": "..."
}
```

- ANSWER·ASK·ABSTAIN은 모두 `200`이다. 누락·공백 질문도 자동 422가 아닌 ASK `200`을 반환한다.
- DB·근거·provider 장애 또는 내부 deadline 초과는 같은 다섯 필드로 `503`을 반환하며 비밀·stack trace를 노출하지 않는다.
- 외부 평가 timeout은 300초, 애플리케이션의 기본 내부 deadline은 `120`초다. `POST /answer`는 `405`다.
- `GET /health/live`는 프로세스만 확인하고, `GET /health/ready`는 DB·migration·active dataset·ontology/registry·provider의 캐시된 상태를 확인한다.
- QuerySpec은 질문 해시+prompt/schema 버전, retrieval은 QuerySpec 해시+dataset/external 버전 키를 써서 단일 VM bounded cache에서 재사용한다. Answer cache는 비활성이다.

---

## 테스트 · Lint · Type Check

```powershell
python -m pytest tests/unit tests/integration
python -m ruff check .
python -m mypy app scripts
python -c "from app.main import app; print(app.title)"
```

통합 테스트(`tests/integration`)는 PostgreSQL/pgvector가 필요하며, 미기동 시 자동 skip

## Golden E2E · 성능 하드닝 (Step 11)

```powershell
# CLOVA Studio 호출 없음: 결정적 QuerySpec → retrieval → evidence → answer guard 전수 검증
python -m scripts.run_golden --provider mock

# cold/warm E2E 성능 측정, 보고서에는 원문 질문/답변/근거를 기록하지 않음
python -m scripts.run_benchmark --runs 1

# Golden 50/50 및 warm p50/p95 기준 확인
python -m scripts.check_release_gate
```

실제 HCX Golden 반복 실행은 크레딧을 사용할 수 있으므로 `--provider hyperclova --allow-billable-hcx`를 명시해야 한다. 금융 evidence를 새로 전송하는 실행은 사용자 승인 후에만 수행한다.

---

## 환경변수

`.env.example` 참고

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `APP_ENV` | `development` | `development` / `test` / `evaluation` |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/product_finder` | PostgreSQL |
| `SOURCE_DATA_DIR` | `../데이터셋` | resource/ 기준 상대경로 |
| `LLM_PROVIDER` | `mock` | `mock` / `hyperclova` |
| `HCX_API_KEY` | 빈 값 | HyperCLOVA X API 키. `.env`에만 보관하고 출력·커밋 금지 |
| `HCX_BASE_URL` | `https://clovastudio.stream.ntruss.com` | CLOVA Studio API base URL |
| `HCX_INTENT_MODEL` / `HCX_ANSWER_MODEL` | `HCX-007` | evaluation에서는 HCX-007만 허용 |
| `BILLING_MODE` | `credit_only` | 기본값. 유료 결제 승인 없이 HCX 호출을 허용하지 않음 |
| `CREDIT_BALANCE_CONFIRMED` | `false` | 콘솔에서 크레딧 잔액·만료일을 확인한 당일에만 `true`; 그 전에는 실제 HCX 호출 차단 |
| `INTERNAL_TIMEOUT_SECONDS` | `120` | `/answer` 전체 내부 deadline(300 미만) |
| `MAX_QUESTION_LENGTH` | `4000` | 실행 없이 ASK로 처리할 질문 길이 상한 |
| `CACHE_CAPACITY` | `128` | QuerySpec·retrieval bounded cache 항목 수 |
| `READINESS_CACHE_SECONDS` | `30` | readiness 의존성 재검증 주기 |

### HCX 비용 통제

`CLOVA Studio`는 크레딧 적용 대상이더라도 토큰 기준의 유료 API다. 크레딧이 유효하면 그 잔액에서 사용액이 차감되며, 크레딧이 없거나 만료되면 실제 결제 가능성이 있다. 이 저장소는 기본 `credit_only` guard로 잔액·만료일의 수동 확인 전 실제 호출을 차단한다. 상세 절차는 [HCX 크레딧 전용 호출 정책](docs/hcx_credit_only_policy.md)을 따른다.

---

## 디렉터리 구조

```text
resource/
  app/data/          # manifest, validator, ingestion, raw models
  app/curated/       # mappers, quality, builder, curated models
  app/query/         # QuerySpec, field registry, semantic validator
  app/retrieval/     # SqlRetriever, RelationRetriever, DocumentRetriever
  app/agent/         # PolicyEngine, Orchestrator, merger, decision
  app/external/      # snapshot ingestion, entity resolution, coverage
  app/embedding/     # DeterministicEmbeddingProvider (Step 10 전 테스트용)
  app/llm/           # LlmProvider, MockLlmProvider
  ontology/          # TTL 5종, field_registry.yaml, synonyms.yaml
  data/manifests/    # source_manifest.json (SHA-256 기준선)
  data/external/     # frozen external snapshot (manifest, normalized, targets)
  deploy/            # docker-compose.dev.yml
  alembic/           # DB migration
  scripts/           # ingest, validate, benchmark, external snapshot CLI
  tests/
```

원본 Excel은 상위 `데이터셋/`에 두며 수정하지 않음
