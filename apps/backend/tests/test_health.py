"""Tests for safe liveness, readiness, and runtime health contracts."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db_session, get_redis
from app.core.config import Settings
from app.core.worker_health import (
    WORKER_HEARTBEAT_KEY,
    build_worker_heartbeat,
    parse_worker_heartbeat,
)
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
        "draft_provider": "fake",
        "draft_model": "fake-static-v1",
        "draft_available": False,
        "email_send_enabled": False,
        "environment": "development",
        "real_data_gate": "blocked",
    }
    payload = response.text.lower()
    assert "key" not in payload
    assert "base_url" not in payload
    assert "sk-" not in payload


async def test_runtime_status_reports_deepseek_draft_capability() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        email_generator_provider="deepseek",
        deepseek_api_key="sk-test-not-real",
        deepseek_model="deepseek-v4-pro",
        deepseek_base_url="https://api.deepseek.com",
        research_extractor_provider="deepseek",
    )
    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/health/runtime")
        assert response.status_code == 200
        body = response.json()
        assert body["research_provider"] == "deepseek"
        assert body["draft_provider"] == "deepseek"
        assert body["draft_model"] == "deepseek-v4-pro"
        assert body["draft_available"] is True
        assert body["email_send_enabled"] is False
        assert body["real_data_gate"] == "blocked"


def _heartbeat(age_seconds: float) -> str:
    now = datetime.now(UTC) - timedelta(seconds=age_seconds)
    return build_worker_heartbeat("worker-host:1:abcdef12", now)


class _Session:
    def __init__(self, *, healthy: bool) -> None:
        self.healthy = healthy

    async def execute(self, _statement: object) -> None:
        if not self.healthy:
            raise RuntimeError("sensitive database connection detail")


class _Redis:
    def __init__(
        self,
        *,
        healthy: bool = True,
        worker_payload: str | None = None,
        worker_missing: bool = False,
    ) -> None:
        self.healthy = healthy
        self.worker_payload = worker_payload
        self.worker_missing = worker_missing

    async def ping(self) -> bool:
        if not self.healthy:
            raise RuntimeError("sensitive redis connection detail")
        return True

    async def exists(self, key: str) -> int:
        assert key == WORKER_HEARTBEAT_KEY
        if self.worker_missing:
            return 0
        return int(self.worker_payload is not None)

    async def get(self, key: str) -> str | None:
        assert key == WORKER_HEARTBEAT_KEY
        return self.worker_payload


async def _readiness_client(
    *,
    database: bool = True,
    redis: bool = True,
    redis_mock: _Redis | None = None,
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None))

    async def session_override() -> AsyncIterator[_Session]:
        yield _Session(healthy=database)

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_redis] = lambda: redis_mock or _Redis(
        healthy=redis,
        worker_payload=_heartbeat(1),
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
    body = response.json()
    assert body["status"] == "ready"
    postgres = next(item for item in body["dependencies"] if item["name"] == "postgres")
    redis = next(item for item in body["dependencies"] if item["name"] == "redis")
    worker = next(item for item in body["dependencies"] if item["name"] == "worker")
    # Backward compatibility: postgres/redis keep the original shape exactly.
    assert postgres == {"name": "postgres", "healthy": True, "detail": None}
    assert redis == {"name": "redis", "healthy": True, "detail": None}
    assert worker["healthy"] is True
    assert worker["status"] == "healthy"
    assert worker["reason_code"] == "WORKER_HEARTBEAT_OK"
    assert worker["last_seen_at"] is not None
    assert worker["age_seconds"] <= 1.1


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
    assert "redis://" not in response.text
    assert "change-me" not in response.text


async def test_readiness_reports_missing_worker_heartbeat() -> None:
    mock = _Redis(worker_payload=_heartbeat(1), worker_missing=True)
    async for client in _readiness_client(redis_mock=mock):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    worker = next(item for item in body["dependencies"] if item["name"] == "worker")
    assert worker == {
        "name": "worker",
        "healthy": False,
        "detail": "worker heartbeat missing",
        "status": "unavailable",
        "reason_code": "WORKER_HEARTBEAT_MISSING",
        "last_seen_at": None,
        "age_seconds": None,
    }


async def test_readiness_reports_expired_worker_heartbeat() -> None:
    mock = _Redis(worker_payload=_heartbeat(30))
    async for client in _readiness_client(redis_mock=mock):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    worker = next(item for item in body["dependencies"] if item["name"] == "worker")
    assert worker["healthy"] is False
    assert worker["status"] == "unavailable"
    assert worker["reason_code"] == "WORKER_HEARTBEAT_EXPIRED"
    assert worker["last_seen_at"] is not None
    assert worker["age_seconds"] is not None and worker["age_seconds"] >= 29.9


async def test_readiness_reports_invalid_worker_heartbeat_payload() -> None:
    mock = _Redis(worker_payload="not-json")
    async for client in _readiness_client(redis_mock=mock):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    worker = next(item for item in body["dependencies"] if item["name"] == "worker")
    assert worker == {
        "name": "worker",
        "healthy": False,
        "detail": "worker heartbeat payload invalid",
        "status": "unavailable",
        "reason_code": "WORKER_HEARTBEAT_INVALID",
        "last_seen_at": None,
        "age_seconds": None,
    }


async def test_readiness_reports_unknown_worker_when_redis_unavailable() -> None:
    async for client in _readiness_client(redis=False):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    worker = next(item for item in body["dependencies"] if item["name"] == "worker")
    assert worker == {
        "name": "worker",
        "healthy": False,
        "detail": "worker status unknown because Redis is unavailable",
        "status": "unknown",
        "reason_code": "REDIS_UNAVAILABLE",
        "last_seen_at": None,
        "age_seconds": None,
    }
    assert "sensitive" not in response.text
    assert "redis://" not in response.text


async def test_worker_recovers_after_heartbeat_returns() -> None:
    mock = _Redis(worker_payload=None, worker_missing=True)
    app = create_app(Settings(_env_file=None))

    async def session_override() -> AsyncIterator[_Session]:
        yield _Session(healthy=True)

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_redis] = lambda: mock
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.get("/api/v1/health/ready")
        first_worker = next(
            item for item in first.json()["dependencies"] if item["name"] == "worker"
        )
        assert first_worker["reason_code"] == "WORKER_HEARTBEAT_MISSING"

        mock.worker_missing = False
        mock.worker_payload = _heartbeat(1)
        second = await client.get("/api/v1/health/ready")
        second_worker = next(
            item for item in second.json()["dependencies"] if item["name"] == "worker"
        )
        assert second.json()["status"] == "ready"
        assert second_worker["status"] == "healthy"
        assert second_worker["reason_code"] == "WORKER_HEARTBEAT_OK"


def test_worker_heartbeat_payload_roundtrip() -> None:
    now = datetime.now(UTC)
    payload = build_worker_heartbeat("host:1:abc", now)
    parsed = parse_worker_heartbeat(payload)
    assert parsed is not None
    assert parsed["owner"] == "host:1:abc"
    assert parsed["heartbeat_at"] == now.isoformat()


def test_worker_heartbeat_rejects_invalid_payloads() -> None:
    for payload in (None, "", "not-json", "[]", "{}", '{"owner":"x"}', '{"heartbeat_at":"x"}'):
        assert parse_worker_heartbeat(payload) is None
