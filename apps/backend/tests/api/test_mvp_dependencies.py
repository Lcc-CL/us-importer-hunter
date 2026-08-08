"""Email generator selection and local-only CORS boundaries."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_email_draft_generator
from app.core.config import Settings
from app.domain.services import EmailGenerationContext
from app.main import create_app
from app.services.email import (
    EmailGenerationError,
    FakeEmailDraftGenerator,
    OpenAIEmailDraftGenerator,
)
from app.shared.exceptions import ProviderUnavailableError


def context() -> EmailGenerationContext:
    return EmailGenerationContext(
        company_name="Pacific Home Goods",
        website="https://phg.example",
        contact_name="Maria Chen",
        contact_title="Director of Supply Chain",
        opportunity_score=80.0,
        qualification_decision="qualified",
        opportunity_reasons=("evidence-backed import activity",),
        available_evidence=("customs shipments recorded",),
        sender_name="Alex",
        sender_company="Harbor Logistics",
        sender_value_proposition="Reliable inbound freight support.",
    )


def test_fake_is_default_and_requires_no_openai_key() -> None:
    settings = Settings(_env_file=None, openai_api_key="")
    generator = get_email_draft_generator(settings)
    assert isinstance(generator, FakeEmailDraftGenerator)


async def test_openai_missing_key_fails_only_when_generation_is_called() -> None:
    settings = Settings(
        _env_file=None,
        email_generator_provider="openai",
        openai_api_key="",
    )
    generator = get_email_draft_generator(settings)
    assert isinstance(generator, OpenAIEmailDraftGenerator)
    with pytest.raises(EmailGenerationError, match="OPENAI_API_KEY is not configured"):
        await generator.generate(context())


async def test_deepseek_draft_generator_is_wired_without_second_sdk() -> None:
    settings = Settings(
        _env_file=None,
        email_generator_provider="deepseek",
        deepseek_api_key="sk-test-not-real",
        deepseek_model="deepseek-v4-pro",
        deepseek_base_url="https://api.deepseek.com",
    )
    generator = get_email_draft_generator(settings)
    assert isinstance(generator, OpenAIEmailDraftGenerator)
    assert generator.provider_name == "deepseek"
    assert generator.model_name == "deepseek-v4-pro"

    with pytest.raises(ProviderUnavailableError, match="DEEPSEEK_API_KEY"):
        get_email_draft_generator(
            Settings(
                _env_file=None,
                email_generator_provider="deepseek",
                deepseek_api_key="",
                deepseek_model="deepseek-v4-pro",
                deepseek_base_url="https://api.deepseek.com",
            )
        )


async def test_cors_allows_local_frontend_only() -> None:
    app = create_app(Settings(_env_file=None))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        allowed = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers
