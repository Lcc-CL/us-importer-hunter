"""Shared test fixtures."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Isolated settings for tests — never reads the developer's .env."""
    return Settings(_env_file=None, app_env="development", debug=False)


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """HTTP client against the app, without external infrastructure.

    Uses the raw ASGI app (no lifespan), so only endpoints that don't
    require DB/Redis can be exercised here.
    """
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
