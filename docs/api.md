# 평가 API 운영 계약

평가 API는 인증 없는 `GET /answer`만 제공한다. `POST /answer`는 허용하지 않는다.

```text
GET /answer?question_id=...&question=...
```

응답은 정확히 다섯 문자열 필드다.

```json
{
  "question_id": "...",
  "question": "...",
  "retrieved_context": "...",
  "think_trace": "...",
  "answer": "..."
}
```

- ANSWER, ASK, ABSTAIN은 정상 `200`이다.
- 빈 질문/길이 초과는 `ASK` 200으로 응답한다.
- DB·근거·provider·deadline 장애는 같은 다섯 필드를 유지한 `503`으로 매핑하며, secret/stack trace는 반환하지 않는다.
- `/health/live`는 프로세스만, `/health/ready`는 DB·migration·활성 데이터셋·ontology·provider 준비상태를 확인한다. readiness는 HCX 생성 요청을 반복하지 않는다.

`think_trace`에는 실행 단계와 hash/version만 보존한다. 사고 과정, API key, 원문 prompt는 포함하지 않는다.
