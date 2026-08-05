"""Tests for safe liveness, readiness, and runtime health contracts."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db_session, get_redis
from app.core.config import Settings
from app.core.worker_health import WORKER_HEARTBEAT_KEY
from app.main import create_app


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
        "real_data_gate": "blocked",
    }
    payload = response.text.lower()
    assert "key" not in payload
    assert "base_url" not in payload
    assert "sk-" not in payload


class _Session:
    def __init__(self, *, healthy: bool) -> None:
        self.healthy = healthy

    async def execute(self, _statement: object) -> None:
        if not self.healthy:
            raise RuntimeError("sensitive database connection detail")


class _Redis:
    def __init__(self, *, healthy: bool = True, worker: bool = True) -> None:
        self.healthy = healthy
        self.worker = worker

    async def ping(self) -> bool:
        if not self.healthy:
            raise RuntimeError("sensitive redis connection detail")
        return True

    async def exists(self, key: str) -> int:
        assert key == WORKER_HEARTBEAT_KEY
        return int(self.worker)


async def _readiness_client(
    *,
    database: bool = True,
    redis: bool = True,
    worker: bool = True,
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None))

    async def session_override() -> AsyncIterator[_Session]:
        yield _Session(healthy=database)

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_redis] = lambda: _Redis(
        healthy=redis,
        worker=worker,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


async def test_readiness_reports_database_redis_and_worker_healthy() -> None:
    async for client in _readiness_client():
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": [
            {"name": "postgres", "healthy": True, "detail": None},
            {"name": "redis", "healthy": True, "detail": None},
            {"name": "worker", "healthy": True, "detail": None},
        ],
    }


async def test_readiness_sanitizes_database_failure() -> None:
    async for client in _readiness_client(database=False):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    postgres = next(item for item in body["dependencies"] if item["name"] == "postgres")
    assert postgres == {
        "name": "postgres",
        "healthy": False,
        "detail": "database connection check failed",
    }
    assert "sensitive" not in response.text


async def test_readiness_reports_missing_worker_heartbeat() -> None:
    async for client in _readiness_client(worker=False):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    worker = next(item for item in body["dependencies"] if item["name"] == "worker")
    assert worker == {
        "name": "worker",
        "healthy": False,
        "detail": "worker heartbeat missing or expired",
    }
