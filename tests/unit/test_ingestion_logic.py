from __future__ import annotations

from app.data.ingestion import _payload_fingerprint


def test_payload_fingerprint_detects_differences() -> None:
    first = _payload_fingerprint({"pd_no": "P1", "applied_yield": 1.0})
    second = _payload_fingerprint({"pd_no": "P1", "applied_yield": 2.0})
    assert first != second


def test_payload_fingerprint_is_stable() -> None:
    payload = {"pd_no": "P1", "amount": 0}
    assert _payload_fingerprint(payload) == _payload_fingerprint(payload)
