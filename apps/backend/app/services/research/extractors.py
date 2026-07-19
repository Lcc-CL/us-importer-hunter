"""Research extractors: the protocol and the deterministic fake.

Mirrors the EmailDraftGenerator split (ADR-0023): a domain protocol, a fake
that needs no network, and — in a later phase — a provider-backed
implementation. The fake keeps `make e2e` free and makes tests deterministic.

The real extractor is deliberately absent in phase 2.
"""

import re
from dataclasses import dataclass
from typing import Protocol

from app.domain.research import (
    ExtractionResult,
    ExtractorIdentity,
    OutputLanguage,
    ProposedClaim,
    ResearchProfile,
)

FAKE_PROMPT_VERSION = "research-extract-fake-v1"


@dataclass(frozen=True)
class ExtractionInput:
    """Everything an extractor may look at — nothing else.

    Page text is untrusted data (ADR-0025 §6). The set of pages is frozen
    before extraction, so an extractor cannot cause new fetches: the only URLs
    it may cite are the ones listed here.
    """

    company_name: str
    website: str
    pages: tuple[tuple[str, str], ...]  # (url, cleaned_text)
    #: Language for conclusions only. Evidence snippets are never translated.
    output_language: OutputLanguage = OutputLanguage.EN_US


class ResearchExtractor(Protocol):
    """Turns fetched page text into a profile and proposed claims."""

    @property
    def identity(self) -> ExtractorIdentity: ...

    async def extract(self, payload: ExtractionInput) -> ExtractionResult: ...


# Keyword → claim kind. Deterministic and English-only on purpose: the fake
# exists to exercise the pipeline, not to be good at extraction.
_RULES: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("import_activity", ("import", "customs", "shipment", "container"), 0.8),
    ("china_dependency", ("china", "chinese", "shenzhen", "guangdong"), 0.7),
    ("shipping_fit", ("fcl", "lcl", "ocean freight", "40hq", "air freight"), 0.8),
    ("cargo_value_potential", ("high value", "premium", "million"), 0.6),
    ("company_scale", ("warehouse", "employees", "facility", "sq ft"), 0.6),
    ("growth_signal", ("growing", "expand", "hiring", "increase"), 0.7),
    ("logistics_complexity", ("multi-origin", "suppliers", "distribution center"), 0.6),
    ("pain_point", ("delay", "shortage", "bottleneck", "lead time"), 0.5),
)

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")

#: Chinese labels for the fake's claim kinds. The Fake must speak both
#: languages or `make e2e` would pass on behaviour the real provider does not
#: have — the exact drift the fake exists to prevent.
_ZH_KIND_LABELS: dict[str, str] = {
    "import_activity": "进口活动",
    "china_dependency": "中国供应链依赖",
    "shipping_fit": "运输匹配",
    "cargo_value_potential": "货值潜力",
    "company_scale": "企业规模",
    "growth_signal": "增长信号",
    "logistics_complexity": "物流复杂度",
    "pain_point": "潜在痛点",
}


class FakeResearchExtractor:
    """Deterministic, offline, and honest: every claim it proposes quotes a
    sentence that really exists in the page it cites, so the validator accepts
    it. Same input → same output, always."""

    @property
    def identity(self) -> ExtractorIdentity:
        return ExtractorIdentity(
            provider="fake", model="fake-research-v1", prompt_version=FAKE_PROMPT_VERSION
        )

    async def extract(self, payload: ExtractionInput) -> ExtractionResult:
        claims: list[ProposedClaim] = []
        products: list[str] = []
        seen_kinds: set[str] = set()

        for url, text in payload.pages:
            for sentence in self._sentences(text):
                lowered = sentence.lower()
                for kind, keywords, confidence in _RULES:
                    if kind in seen_kinds:
                        continue
                    if any(keyword in lowered for keyword in keywords):
                        claims.append(
                            ProposedClaim(
                                kind=kind,
                                detail=self._detail(kind, sentence, payload.output_language),
                                # Never localized: it must stay a verbatim
                                # substring of the page for the validator.
                                evidence_snippet=sentence,
                                source_url=url,
                                confidence=confidence,
                            )
                        )
                        seen_kinds.add(kind)
                        break
            if "product" in text.lower() and len(products) < 3:
                products.append(
                    "站点提及的产品"
                    if payload.output_language is OutputLanguage.ZH_CN
                    else "products mentioned on site"
                )

        found = {claim.kind for claim in claims}
        unknown = tuple(
            sorted(kind for kind, _, _ in _RULES if kind not in found and kind != "pain_point")
        )

        first_text = payload.pages[0][1] if payload.pages else ""
        summary = self._sentences(first_text)[0] if self._sentences(first_text) else None

        zh = payload.output_language is OutputLanguage.ZH_CN
        return ExtractionResult(
            profile=ResearchProfile(
                summary=(f"网站摘要：{summary}" if zh and summary else summary),
                industry=None,
                products=tuple(products),
                mentions_importing="import" in first_text.lower(),
            ),
            claims=tuple(claims),
            unknown_dimensions=unknown,
            notes=(
                (
                    "由 FakeResearchExtractor 生成——无网络请求，无模型调用"
                    if zh
                    else "generated by FakeResearchExtractor — no network, no model"
                ),
            ),
        )

    @staticmethod
    def _detail(kind: str, sentence: str, language: OutputLanguage) -> str:
        if language is OutputLanguage.ZH_CN:
            return f"{_ZH_KIND_LABELS.get(kind, kind)}：{sentence}"
        return f"{kind.replace('_', ' ')}: {sentence}"

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [
            candidate.strip()
            for candidate in _SENTENCE.findall(text)
            if len(candidate.strip()) >= 20
        ]
