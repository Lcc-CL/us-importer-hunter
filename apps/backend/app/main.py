"""Application entrypoint: app factory and lifespan wiring."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.redis import create_redis_client
from app.database.session import create_engine, create_session_factory
from app.observability.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and dispose shared infrastructure clients."""
    settings: Settings = app.state.settings

    engine = create_engine(settings.database_url, echo=settings.debug)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = create_redis_client(settings.redis_url)

    yield

    await app.state.redis.aclose()
    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application. Accepts settings injection for tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="US Importer Hunter API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
