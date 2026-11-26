"""Regression checks for the public interview demo and provider boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis
from app.core.config import Settings
from app.main import create_app
from app.providers.kimi import kimi_demo_generator
from app.services.email.interview_demo import CASE


async def test_demo_defaults_to_preset_without_redis(client: AsyncClient) -> None:
    response = await client.get("/api/v1/interview-demo/capability")
    assert response.json() == {"live_enabled": False}


async def test_disabled_demo_draft_does_not_use_redis() -> None:
    app = create_app(Settings(_env_file=None, kimi_demo_max_attempts=0))
    store = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/v1/interview-demo/draft")).status_code == 503
    store.get.assert_not_awaited()
    store.eval.assert_not_awaited()


async def test_kimi_reuses_structured_email_adapter_with_capped_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = kimi_demo_generator("test-value", "moonshot-v1-8k")
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"subject":"Demo","body":"Example draft"}')
                )
            ]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    build = Mock(return_value=client)
    monkeypatch.setattr("openai.AsyncOpenAI", build)
    result = await generator.generate(CASE)
    assert result.subject == "Demo"
    assert build.call_args.kwargs["max_retries"] == 0
    assert build.call_args.kwargs["base_url"] == "https://api.moonshot.ai/v1"
    assert create.call_args.kwargs["model"] == "moonshot-v1-8k"
    assert create.call_args.kwargs["max_tokens"] == 450
    assert create.call_args.kwargs["response_format"] == {"type": "json_object"}
