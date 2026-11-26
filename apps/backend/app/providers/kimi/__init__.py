"""Bounded Moonshot API adapter for the fixed interview demo."""

from app.services.email.generators import OpenAIEmailDraftGenerator


def kimi_demo_generator(api_key: str, model: str) -> OpenAIEmailDraftGenerator:
    return OpenAIEmailDraftGenerator(
        api_key=api_key,
        model=model,
        provider="kimi",
        base_url="https://api.moonshot.ai/v1",
        timeout_seconds=8.0,
        max_output_tokens=450,
        max_retries=0,
    )
