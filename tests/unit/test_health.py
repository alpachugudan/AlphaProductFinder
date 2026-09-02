from __future__ import annotations

from fastapi.testclient import TestClient


def test_live_health_returns_200(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "service": "miraeasset-product-finder",
        "version": "0.1.0",
        "environment": "test",
    }


def test_live_health_response_model_fields(client: TestClient) -> None:
    response = client.get("/health/live")
    data = response.json()
    assert set(data.keys()) == {"status", "service", "version", "environment"}


def test_correlation_id_header_echoed(client: TestClient) -> None:
    correlation_id = "test-correlation-123"
    response = client.get("/health/live", headers={"X-Correlation-ID": correlation_id})
    assert response.headers.get("X-Correlation-ID") == correlation_id


def test_correlation_id_generated_when_missing(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.headers.get("X-Correlation-ID")


def test_app_import_smoke() -> None:
    from app.main import app

    assert app.title == "miraeasset-product-finder"
