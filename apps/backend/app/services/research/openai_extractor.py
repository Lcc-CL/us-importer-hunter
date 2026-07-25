"""OpenAIResearchExtractor: the provider-backed claim extractor (phase 5).

Mirrors OpenAIEmailDraftGenerator (ADR-0023): the OpenAI SDK is imported
lazily inside the client builder, SDK types never cross this module's
boundary, and every failure leaves as a typed ExtractionError.

Three rules this module exists to keep:

1. **One primary request per research run.** At most one controlled retry,
   and only for 429 / 5xx. A timeout, a bad key, or unusable JSON is final —
   retrying those just burns money and latency.
2. **Strict parsing, never guessing.** Malformed structure is reported, not
   repaired. Nothing is inferred from prose: if the model did not return
   valid JSON in the agreed shape, we raise instead of salvaging.
3. **No silent fallback.** A failed real extraction never quietly becomes a
   Fake result; the caller sees the error code.

What the model proposes is still only a proposal — ClaimValidator remains the
anti-hallucination gate, and this module deliberately does not pre-filter
claim kinds, URLs, or snippets so that the validator's rejection warnings stay
the single, measurable record of extractor quality.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from app.domain.research import (
    ALLOWED_CLAIM_KINDS,
    ExtractionResult,
    ExtractorIdentity,
    ProposedClaim,
    ResearchProfile,
)
from app.prompts.research.website_research import (
    PROMPT_VERSION,
    build_user_prompt,
    system_prompt_for,
)
from app.services.research.extractors import ExtractionInput

logger = logging.getLogger(__name__)

#: Total request attempts, i.e. one primary call plus one controlled retry.
MAX_ATTEMPTS = 2


class ExtractionErrorCode(StrEnum):
    """Every way extraction can fail, as a stable, loggable code."""

    TIMEOUT = "extractor_timeout"
    AUTH_FAILED = "extractor_auth_failed"
    RATE_LIMITED = "extractor_rate_limited"
    PROVIDER_ERROR = "extractor_provider_error"
    INVALID_JSON = "extractor_invalid_json"
    SCHEMA_INVALID = "extractor_schema_invalid"
    EMPTY_RESULT = "extractor_empty_result"


#: Only transient server-side conditions may be retried.
_RETRYABLE = frozenset({ExtractionErrorCode.RATE_LIMITED, ExtractionErrorCode.PROVIDER_ERROR})


class ExtractionError(Exception):
    """Extraction failed. Carries a code the caller can map without parsing
    text. The message never contains credentials or page content."""

    def __init__(self, code: ExtractionErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code

    @property
    def retryable(self) -> bool:
        return self.code in _RETRYABLE


@dataclass(frozen=True)
class ExtractionUsage:
    """Observability only — never persisted, never sent to the model."""

    latency_seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class OpenAIResearchExtractor:
    """Provider-backed ResearchExtractor.

    The model is injected, never defaulted here: a wrong-but-plausible model
    name silently costing money is worse than a startup error.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        prompt_version: str = PROMPT_VERSION,
        timeout_seconds: float = 30.0,
        max_input_chars: int = 24_000,
        provider: str = "openai",
        extra_body: dict[str, Any] | None = None,
        client: object | None = None,  # test seam: .chat.completions.create
    ) -> None:
        if not model.strip():
            raise ExtractionError(
                ExtractionErrorCode.PROVIDER_ERROR,
                "no research model configured — set RESEARCH_MODEL or OPENAI_MODEL",
            )
        self._model = model.strip()
        self._provider = provider.strip() or "openai"
        self._extra_body = extra_body
        self._api_key = api_key
        self._base_url = (base_url or "").strip() or None
        self._prompt_version = prompt_version.strip() or PROMPT_VERSION
        self._timeout = timeout_seconds
        self._max_input_chars = max_input_chars
        self._client = client
        self.last_usage: ExtractionUsage | None = None

    @property
    def identity(self) -> ExtractorIdentity:
        return ExtractorIdentity(
            provider=self._provider, model=self._model, prompt_version=self._prompt_version
        )

    async def extract(self, payload: ExtractionInput) -> ExtractionResult:
        client: Any = self._client or self._build_client()
        user_prompt = build_user_prompt(
            company_name=payload.company_name,
            website=payload.website,
            pages=payload.pages,
            max_total_chars=self._max_input_chars,
        )

        started = time.monotonic()
        content, usage = await self._request(
            client, user_prompt, system_prompt_for(payload.output_language)
        )
        self.last_usage = self._usage(usage, time.monotonic() - started)
        return self._parse(content)

    # -- provider call ----------------------------------------------------

    async def _request(
        self, client: Any, user_prompt: str, system_prompt: str
    ) -> tuple[str | None, Any]:
        """At most MAX_ATTEMPTS calls; only 429/5xx justify the second one."""
        last: ExtractionError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            request_kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "timeout": self._timeout,
            }
            if self._extra_body:
                request_kwargs["extra_body"] = self._extra_body
            try:
                response: Any = await client.chat.completions.create(**request_kwargs)
            except ExtractionError:
                raise
            except Exception as exc:  # SDK errors never leak past this boundary
                error = _classify(exc)
                if error.retryable and attempt < MAX_ATTEMPTS:
                    logger.warning(
                        "research extraction retrying after %s (attempt %d/%d)",
                        error.code.value,
                        attempt,
                        MAX_ATTEMPTS,
                    )
                    last = error
                    continue
                raise error from exc
            return self._content_of(response), getattr(response, "usage", None)

        raise last or ExtractionError(
            ExtractionErrorCode.PROVIDER_ERROR, "extraction exhausted its attempts"
        )

    @staticmethod
    def _content_of(response: Any) -> str | None:
        try:
            choices = response.choices
            if not choices:
                raise ExtractionError(
                    ExtractionErrorCode.EMPTY_RESULT, "provider returned no choices"
                )
            content = choices[0].message.content
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(
                ExtractionErrorCode.SCHEMA_INVALID,
                f"provider response had an unexpected shape: {type(exc).__name__}",
            ) from exc
        return content if content is None else str(content)

    @staticmethod
    def _usage(usage: Any, latency: float) -> ExtractionUsage:
        def field(name: str) -> int | None:
            value = getattr(usage, name, None)
            return value if isinstance(value, int) else None

        return ExtractionUsage(
            latency_seconds=round(latency, 3),
            prompt_tokens=field("prompt_tokens"),
            completion_tokens=field("completion_tokens"),
            total_tokens=field("total_tokens"),
        )

    def _build_client(self) -> Any:
        api_key = (self._api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise ExtractionError(
                ExtractionErrorCode.AUTH_FAILED,
                "OPENAI_API_KEY is not configured — set it before running real research",
            )
        from openai import AsyncOpenAI  # imported here: startup never needs it

        if self._base_url:
            return AsyncOpenAI(api_key=api_key, base_url=self._base_url, timeout=self._timeout)
        return AsyncOpenAI(api_key=api_key, timeout=self._timeout)

    # -- strict parsing ---------------------------------------------------

    def _parse(self, content: str | None) -> ExtractionResult:
        if content is None or not content.strip():
            raise ExtractionError(
                ExtractionErrorCode.EMPTY_RESULT, "provider returned an empty message"
            )

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                ExtractionErrorCode.INVALID_JSON, f"response was not valid JSON: {exc.msg}"
            ) from exc

        if not isinstance(payload, dict):
            raise ExtractionError(
                ExtractionErrorCode.SCHEMA_INVALID, "top-level JSON value is not an object"
            )

        notes: list[str] = []
        profile = self._profile(payload.get("company_profile"))
        claims = self._claims(payload.get("claims"), notes)
        unknown = self._unknown_dimensions(payload.get("unknown_dimensions"), notes)
        notes.extend(self._strings(payload.get("warnings"), "warnings"))

        if not claims and not unknown and profile == ResearchProfile():
            raise ExtractionError(
                ExtractionErrorCode.EMPTY_RESULT,
                "response contained no claims, no profile and no unknown dimensions",
            )

        return ExtractionResult(
            profile=profile,
            claims=tuple(claims),
            unknown_dimensions=tuple(unknown),
            notes=tuple(notes),
        )

    @staticmethod
    def _profile(raw: object) -> ResearchProfile:
        if raw is None:
            return ResearchProfile()
        if not isinstance(raw, dict):
            raise ExtractionError(
                ExtractionErrorCode.SCHEMA_INVALID, "company_profile is not an object"
            )

        def text(key: str) -> str | None:
            value = raw.get(key)
            return value.strip() or None if isinstance(value, str) else None

        def items(key: str) -> tuple[str, ...]:
            value = raw.get(key)
            if not isinstance(value, list):
                return ()
            return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())

        mentions = raw.get("mentions_importing")
        return ResearchProfile(
            summary=text("summary"),
            industry=text("industry"),
            products=items("products"),
            locations=items("locations"),
            size_hint=text("size_hint"),
            year_founded=text("year_founded"),
            mentions_importing=mentions if isinstance(mentions, bool) else None,
        )

    @staticmethod
    def _claims(raw: object, notes: list[str]) -> list[ProposedClaim]:
        """Structure is enforced here; truth is enforced by ClaimValidator.

        A structurally malformed entry is dropped with a note rather than
        repaired — but if the model returned claims and none of them were even
        readable, that is a provider/prompt failure worth surfacing loudly.
        """
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ExtractionError(ExtractionErrorCode.SCHEMA_INVALID, "claims is not a list")

        claims: list[ProposedClaim] = []
        for index, entry in enumerate(raw):
            if not isinstance(entry, dict):
                notes.append(f"claim {index} dropped: not an object")
                continue
            fields = {}
            missing = False
            for key in ("kind", "detail", "source_url", "evidence_snippet"):
                value = entry.get(key)
                if not isinstance(value, str) or not value.strip():
                    notes.append(f"claim {index} dropped: {key} is missing or not a string")
                    missing = True
                    break
                fields[key] = value
            if missing:
                continue
            confidence = entry.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, int | float):
                notes.append(f"claim {index} dropped: confidence is missing or not a number")
                continue
            claims.append(
                ProposedClaim(
                    kind=fields["kind"].strip(),
                    detail=fields["detail"].strip(),
                    evidence_snippet=fields["evidence_snippet"],
                    source_url=fields["source_url"].strip(),
                    confidence=float(confidence),
                )
            )

        if raw and not claims:
            raise ExtractionError(
                ExtractionErrorCode.SCHEMA_INVALID,
                f"all {len(raw)} returned claims were structurally unusable",
            )
        return claims

    @classmethod
    def _unknown_dimensions(cls, raw: object, notes: list[str]) -> list[str]:
        """Only real dimension names survive — this field has no downstream
        validator, so the extractor is its only gate."""
        values = cls._strings(raw, "unknown_dimensions")
        kept: list[str] = []
        for value in values:
            if value in ALLOWED_CLAIM_KINDS:
                kept.append(value)
            else:
                notes.append(f"unknown_dimension {value!r} dropped: not an allowed kind")
        return kept

    @staticmethod
    def _strings(raw: object, field: str) -> list[str]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ExtractionError(
                ExtractionErrorCode.SCHEMA_INVALID, f"{field} is not a list"
            )
        return [item.strip() for item in raw if isinstance(item, str) and item.strip()]


def _classify(exc: Exception) -> ExtractionError:
    """Map an SDK exception to a typed code without importing SDK types.

    Duck-typing on ``status_code`` is deliberate: it is the contract the
    OpenAI SDK's APIStatusError family exposes, and it keeps this module (and
    its tests) free of a hard dependency on the SDK's class hierarchy.
    """
    if isinstance(exc, asyncio.TimeoutError | httpx.TimeoutException):
        return ExtractionError(ExtractionErrorCode.TIMEOUT, "provider request timed out")
    if "timeout" in type(exc).__name__.lower():
        return ExtractionError(ExtractionErrorCode.TIMEOUT, "provider request timed out")

    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status in (401, 403):
            return ExtractionError(
                ExtractionErrorCode.AUTH_FAILED,
                f"provider rejected the credential (HTTP {status})",
            )
        if status == 429:
            return ExtractionError(
                ExtractionErrorCode.RATE_LIMITED, "provider rate limited the request (HTTP 429)"
            )
        if status >= 500:
            return ExtractionError(
                ExtractionErrorCode.PROVIDER_ERROR, f"provider returned HTTP {status}"
            )
        return ExtractionError(
            ExtractionErrorCode.PROVIDER_ERROR, f"provider returned HTTP {status}"
        )

    return ExtractionError(
        ExtractionErrorCode.PROVIDER_ERROR, f"provider call failed: {type(exc).__name__}"
    )
