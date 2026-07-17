"""Email draft generators: the fake (tests/dev) and the OpenAI adapter.

Both implement the domain protocol EmailDraftGenerator and return plain
GeneratedEmail — OpenAI SDK types never cross this module's boundary.
"""

import json
import os
from typing import Any

from app.domain.services import EmailGenerationContext, GeneratedEmail
from app.prompts.sales.first_outreach import SYSTEM_PROMPT, build_user_prompt


class EmailGenerationError(Exception):
    """Generation failed: configuration missing, provider error, or an
    unusable response. Callers roll back; nothing is persisted."""


class FakeEmailDraftGenerator:
    """Deterministic, offline. Same context → same draft, always."""

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-static-v1"

    async def generate(self, context: EmailGenerationContext) -> GeneratedEmail:
        first_fact = (
            context.available_evidence[0]
            if context.available_evidence
            else "your US import operations"
        )
        return GeneratedEmail(
            subject=f"Freight partnership for {context.company_name}",
            body=(
                f"Hi {context.contact_name},\n\n"
                f"I'm {context.sender_name} with {context.sender_company}. "
                f"We noticed {first_fact}. "
                f"{context.sender_value_proposition} "
                "If it's useful, I'd welcome a brief reply or a 15-minute call "
                "to see whether we can support your inbound freight.\n\n"
                f"Best regards,\n{context.sender_name}"
            ),
        )


class OpenAIEmailDraftGenerator:
    """OpenAI adapter. The API key is read lazily at generation time —
    a missing key never blocks application startup (L11)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 30.0,
        client: object | None = None,  # test seam: anything with .chat.completions.create
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._client = client

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(self, context: EmailGenerationContext) -> GeneratedEmail:
        client: Any = self._client or self._build_client()
        try:
            response: Any = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(context)},
                ],
                response_format={"type": "json_object"},
                timeout=self._timeout,
            )
        except EmailGenerationError:
            raise
        except Exception as exc:  # SDK errors never leak past this boundary
            raise EmailGenerationError(f"openai request failed: {exc}") from exc
        return self._parse(response)

    def _build_client(self) -> Any:
        api_key = self._api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise EmailGenerationError(
                "OPENAI_API_KEY is not configured — set it before generating drafts"
            )
        from openai import AsyncOpenAI  # imported here: startup never needs it

        return AsyncOpenAI(api_key=api_key, timeout=self._timeout)

    @staticmethod
    def _parse(response: Any) -> GeneratedEmail:
        try:
            content = response.choices[0].message.content
            payload = json.loads(content)
            return GeneratedEmail(subject=payload["subject"], body=payload["body"])
        except EmailGenerationError:
            raise
        except Exception as exc:
            raise EmailGenerationError(f"openai returned an unusable response: {exc}") from exc
