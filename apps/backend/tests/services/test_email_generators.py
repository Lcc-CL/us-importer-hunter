"""Email draft generators: fake determinism + OpenAI adapter (mocked)."""

import json
from dataclasses import dataclass
from typing import Any

import pytest

from app.domain.services import EmailGenerationContext
from app.services.email import (
    EmailGenerationError,
    FakeEmailDraftGenerator,
    OpenAIEmailDraftGenerator,
)

CONTEXT = EmailGenerationContext(
    company_name="Pacific Home Goods Inc.",
    website="https://phg.com",
    contact_name="Maria Chen",
    contact_title="Director of Supply Chain",
    opportunity_score=78.0,
    qualification_decision="qualified",
    opportunity_reasons=("import-related signal present",),
    available_evidence=("importyeti recorded this company at https://ref/1",),
    sender_name="Alex Liu",
    sender_company="Eastbridge Freight",
    sender_value_proposition="We run weekly FCL consolidations from Shanghai to LA.",
)


class TestFakeGenerator:
    async def test_stable_and_offline(self) -> None:
        generator = FakeEmailDraftGenerator()
        first = await generator.generate(CONTEXT)
        second = await generator.generate(CONTEXT)
        assert first == second
        assert "Pacific Home Goods Inc." in first.subject
        assert "Maria Chen" in first.body
        assert generator.provider_name == "fake"


class _FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self._content = content
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error

        @dataclass
        class Message:
            content: str

        @dataclass
        class Choice:
            message: Message

        @dataclass
        class Response:
            choices: list[Choice]

        assert self._content is not None
        return Response(choices=[Choice(message=Message(content=self._content))])


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        class Chat:
            def __init__(self, completions: _FakeCompletions) -> None:
                self.completions = completions

        self.chat = Chat(completions)


class TestOpenAIAdapter:
    async def test_mocked_generation(self) -> None:
        completions = _FakeCompletions(
            content=json.dumps({"subject": "Freight for PHG", "body": "Hi Maria — short note."})
        )
        generator = OpenAIEmailDraftGenerator(client=_FakeClient(completions))
        email = await generator.generate(CONTEXT)
        assert email.subject == "Freight for PHG"
        assert email.body.startswith("Hi Maria")
        # the prompt carried only context facts, with the version-locked rules
        sent = completions.calls[0]
        assert sent["model"] == "gpt-4o-mini"
        assert "Pacific Home Goods Inc." in sent["messages"][1]["content"]
        assert generator.provider_name == "openai"

    async def test_missing_api_key_fails_lazily(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        generator = OpenAIEmailDraftGenerator()  # constructing never raises (startup-safe)
        with pytest.raises(EmailGenerationError, match="OPENAI_API_KEY"):
            await generator.generate(CONTEXT)

    async def test_sdk_errors_never_leak(self) -> None:
        completions = _FakeCompletions(error=RuntimeError("socket exploded"))
        generator = OpenAIEmailDraftGenerator(client=_FakeClient(completions))
        with pytest.raises(EmailGenerationError, match="openai request failed"):
            await generator.generate(CONTEXT)

    async def test_unusable_response_rejected(self) -> None:
        completions = _FakeCompletions(content="not json at all")
        generator = OpenAIEmailDraftGenerator(client=_FakeClient(completions))
        with pytest.raises(EmailGenerationError, match="unusable response"):
            await generator.generate(CONTEXT)

    async def test_context_fingerprint_is_stable(self) -> None:
        assert CONTEXT.fingerprint() == CONTEXT.fingerprint()
        assert len(CONTEXT.fingerprint()) == 64


class TestDeepSeekAdapter:
    async def test_deepseek_reuses_openai_compatible_transport(self) -> None:
        completions = _FakeCompletions(
            content=json.dumps(
                {"subject": "DeepSeek draft", "body": "Hi — freight partnership note."}
            )
        )
        generator = OpenAIEmailDraftGenerator(
            provider="deepseek",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            client=_FakeClient(completions),
        )
        email = await generator.generate(CONTEXT)
        assert email.subject == "DeepSeek draft"
        assert generator.provider_name == "deepseek"
        assert generator.model_name == "deepseek-v4-pro"
        sent = completions.calls[0]
        assert sent["model"] == "deepseek-v4-pro"

    async def test_deepseek_missing_key_fails_lazily(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        generator = OpenAIEmailDraftGenerator(
            provider="deepseek",
            base_url="https://api.deepseek.com",
        )
        with pytest.raises(EmailGenerationError, match="DEEPSEEK_API_KEY"):
            await generator.generate(CONTEXT)


class TestDepartmentContactDraft:
    async def test_department_salutation_is_used_verbatim(self) -> None:
        """DEPARTMENT_CONTACT mode: the draft greets the team, never an
        invented person — 'Purchasing Team' flows through as the contact name."""
        from dataclasses import replace

        context = replace(CONTEXT, contact_name="Purchasing Team", contact_title=None)
        draft = await FakeEmailDraftGenerator().generate(context)
        assert "Hi Purchasing Team," in draft.body
        assert "Maria Chen" not in draft.body
