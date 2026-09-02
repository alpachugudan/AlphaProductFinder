# NCP 운영 배포 런북

이 서비스는 단일 NCP Ubuntu VM에서 Docker Compose로 실행한다. Nginx만 호스트 포트 `80`을 공개하며 app(`8000`)과 PostgreSQL(`5432`)은 Docker 내부 네트워크에만 둔다.

## 비밀과 데이터

- `.env`: DB 접속정보와 평가 환경 설정. 서버에서만 생성하며 권한은 `600`이다.
- `.hcx-api`: `HCX_API_KEY`만 넣는 별도 서버 파일이다. Git, Docker image, 로그에 넣지 않는다.
- `source-data/`: 원본 Excel 8개를 서버에만 저장한다. GitHub와 Docker image에서 제외한다.
- `backups/`: PostgreSQL custom dump 저장 위치이며 GitHub에 올리지 않는다.

## 일반 배포

```sh
cd /opt/alpha-product-finder
git pull --ff-only
docker compose -f deploy/docker-compose.yml up -d --build app nginx
sh deploy/smoke-health.sh
```

`docker compose down -v`, PostgreSQL volume 삭제, Raw/Curated 초기화는 일반 배포 절차에서 사용하지 않는다.

## HCX 비용 제어

- `BILLING_MODE=credit_only`를 유지한다.
- 크레딧 유효 여부를 배포 당일 확인한 경우에만 `CREDIT_BALANCE_CONFIRMED=true`으로 둔다.
- `HCX_STARTUP_SMOKE_ENABLED=false`가 기본이다. startup smoke는 실제 HCX 요청을 만들므로, 명시적 승인한 단발 검증에만 `true`로 바꾼다.
- `/health/live`, `/health/ready`는 생성 호출을 하지 않는다.
- 실제 `/answer` 검증은 사용자 승인 범위에서만 수행한다.

## 백업과 복구

```sh
cd /opt/alpha-product-finder
sh deploy/backup.sh
```

복구는 빈 대체 DB에서 수행해 검증한 뒤에만 승인 범위에서 전환한다. 기존 운영 volume을 삭제하거나 덮어쓰는 명령은 자동화하지 않는다.
