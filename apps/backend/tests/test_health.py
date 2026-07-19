"""Tests for the liveness endpoint."""

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "us-importer-hunter"
    assert body["environment"] == "development"


async def test_runtime_status_reports_provider_without_secrets(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/health/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "provider": "fake",
        "model": "fake-static-v1",
        "research_provider": "fake",
        "research_model": "fake-research-v1",
        "environment": "development",
    }
    payload = response.text.lower()
    assert "key" not in payload
    assert "base_url" not in payload
    assert "sk-" not in payload
