"""FastAPI dependency providers.

Resources (engine, session factory, redis) live on ``app.state``; these
providers expose them to routes and services via dependency injection.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session scoped to a single request."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
