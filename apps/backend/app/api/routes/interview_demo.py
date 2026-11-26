"""Optional live draft endpoint for the fixed interview case."""

from fastapi import APIRouter, HTTPException
from redis.exceptions import RedisError

from app.api.deps import RedisDep, SettingsDep
from app.providers.kimi import kimi_demo_generator
from app.services.email.generators import EmailGenerationError
from app.services.email.interview_demo import (
    DemoQuotaExceeded,
    InterviewDraft,
    generate_interview_draft,
)

router = APIRouter(prefix="/interview-demo", tags=["interview demo"])


@router.get("/capability")
async def capability(settings: SettingsDep) -> dict[str, bool]:
    return {"live_enabled": settings.kimi_demo_live_enabled}


@router.post("/draft", response_model=InterviewDraft)
async def create_draft(settings: SettingsDep, redis: RedisDep) -> InterviewDraft:
    if not settings.kimi_demo_live_enabled:
        raise HTTPException(503, "Live generation is disabled for this deployment.")
    generator = kimi_demo_generator(
        settings.kimi_api_key.get_secret_value().strip(), settings.kimi_model.strip()
    )
    try:
        return await generate_interview_draft(redis, generator, settings.kimi_demo_max_attempts)
    except DemoQuotaExceeded as exc:
        raise HTTPException(429, "The interview demo request limit has been reached.") from exc
    except RedisError as exc:
        raise HTTPException(503, "The demo cache or quota store is unavailable.") from exc
    except EmailGenerationError as exc:
        raise HTTPException(502, "Kimi did not return a usable draft.") from exc
