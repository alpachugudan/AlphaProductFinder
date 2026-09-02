# HCX 크레딧 전용 호출 정책

## 결론

`CLOVA Studio`는 크레딧 적용 서비스 목록에 포함되어 있어, 유효한 NCP 크레딧이 있으면 HCX API 사용량을 해당 크레딧에서 차감할 수 있다. 그러나 API 호출 자체는 무료가 아니다. 모델·용도·입출력 토큰에 따라 사용 요금이 계산되며, 크레딧 잔액이 없거나 만료되면 실제 결제가 발생할 수 있다.

따라서 이 프로젝트는 **크레딧 전용(`credit_only`) 정책**을 기본값으로 사용한다. 이 정책은 무료 서비스처럼 보이는 표현으로 실제 과금 가능성을 숨기지 않는다.

공식 근거:

- [CLOVA Studio 사용 준비](https://guide.ncloud-docs.com/docs/clovastudio-spec): 모델·용도·토큰 수 기준으로 이용 요금 부과
- [CLOVA Studio 가격표](https://www.ncloud.com/charge/price/ko): 인퍼런스가 토큰 기준 과금됨
- [CLOVA Studio 이용량 제어 정책](https://guide.ncloud-docs.com/docs/clovastudio-ratelimiting): HCX-007의 QPM/TPM은 요청 횟수와 입력+최대 생성 토큰을 기준으로 제한됨

## 실행 규칙

1. NCP 콘솔에서 `CLOVA Studio`가 크레딧 적용 대상인지, **현재 크레딧 잔액과 만료일**이 유효한지를 작업자가 먼저 확인한다.
2. 확인 전에는 `.env`의 `CREDIT_BALANCE_CONFIRMED`를 `false`로 유지한다. 애플리케이션은 이 상태에서 HCX HTTP 호출을 차단한다.
3. 확인을 마친 당일에만 아래처럼 설정한다. API 키와 잔액 금액은 문서·Git·로그에 기록하지 않는다.

   ```dotenv
   BILLING_MODE=credit_only
   CREDIT_BALANCE_CONFIRMED=true
   ```

4. 테스트는 mock HTTP test를 우선 사용한다. 실제 smoke는 승인된 최소 횟수로만 실행하고, `maxCompletionTokens`를 낮게 유지한다.
5. 크레딧이 소진·만료되었거나 잔액을 확인할 수 없으면 `CREDIT_BALANCE_CONFIRMED=false`로 되돌리고 실제 HCX 호출을 중단한다.
6. `BILLING_MODE=allow_paid`는 이 프로젝트의 기본 운영 범위가 아니다. 별도의 명시적 결제 승인 없이는 설정하지 않는다.

## 검증과 관측

- `/health/ready`는 캐시된 provider 상태만 확인하며, 요청마다 토큰을 쓰는 생성 호출을 하지 않는다.
- `APP_ENV=evaluation`은 크레딧 확인값, HCX API 키, HCX-007 모델 설정이 모두 있어야 기동한다. 기동 중 capability smoke는 한 번만 실행된다.
- provider 로그에는 모델, 지연 시간, 토큰 사용량, 재시도 횟수만 남긴다. API 키, 원문 프롬프트, 원문 답변은 남기지 않는다.
