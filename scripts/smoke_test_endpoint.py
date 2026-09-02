from __future__ import annotations

import argparse
import time
from typing import NoReturn

import httpx

EXPECTED_KEYS = {
    "question_id",
    "question",
    "retrieved_context",
    "think_trace",
    "answer",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="평가용 GET /answer 계약 smoke test")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--timeout", type=float, default=130.0)
    return parser.parse_args()


def fail(message: str) -> NoReturn:
    raise SystemExit(f"FAIL: {message}")


def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    started = time.perf_counter()
    try:
        response = httpx.get(
            f"{base_url}/answer",
            params={"question_id": args.question_id, "question": args.question},
            timeout=args.timeout,
        )
    except httpx.HTTPError as exc:
        fail(f"request failed: {exc.__class__.__name__}")
    elapsed = time.perf_counter() - started

    if response.status_code not in {200, 503}:
        fail(f"unexpected status={response.status_code}")
    if not response.headers.get("content-type", "").startswith("application/json"):
        fail("content-type is not application/json")
    try:
        payload = response.json()
    except ValueError:
        fail("response is not valid JSON")
    if set(payload) != EXPECTED_KEYS:
        fail(f"unexpected keys={sorted(payload)}")
    if not all(isinstance(value, str) for value in payload.values()):
        fail("all five response values must be strings")
    if payload["question_id"] != args.question_id or payload["question"] != args.question:
        fail("question echo mismatch")

    print(f"PASS status={response.status_code} elapsed_seconds={elapsed:.3f}")
    print("keys=answer,question,question_id,retrieved_context,think_trace")


if __name__ == "__main__":
    main()
