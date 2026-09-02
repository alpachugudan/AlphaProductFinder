# 제출 체크리스트

제출 직전에 아래 항목을 실행 결과와 함께 기록한다. API 키, DB 비밀번호, 원본 Excel, 전체 금융 질문은 기록하지 않는다.

- [ ] Public base URL의 `GET /health/live`가 `200`
- [ ] `GET /health/ready`의 database, migration, dataset, ontology_registry, llm_provider가 모두 `ok`
- [ ] `GET /answer`가 다섯 개 문자열 필드만 반환
- [ ] 현재 Git commit과 Docker image digest 기록
- [ ] Raw 53,375행, Curated 44,415행, active dataset version 기록
- [ ] 동결 외부지식 manifest hash와 migration head 기록
- [ ] ACG에서 80만 공개, 22는 운영자 IP만 허용, 5432 비공개 확인
- [ ] credit_only, HCX startup smoke 비활성, 크레딧 만료일 확인
- [ ] 최신 PostgreSQL backup 파일과 SHA-256 기록
