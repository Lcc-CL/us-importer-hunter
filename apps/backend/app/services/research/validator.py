"""Claim validation — the anti-hallucination gate (ADR-0025 §5).

Prompt instructions are not enforcement. Everything an extractor proposes is
checked here against what we actually fetched, and anything that fails is
**discarded with a warning**, never downgraded into a low-confidence signal.

Five rules, all mandatory:
  1. kind is in the whitelist;
  2. source_url was fetched by this run;
  3. the cited page belongs to this run;
  4. evidence_snippet really occurs in that page's cleaned text;
  5. confidence is within 0–1.
"""

import re
from dataclasses import dataclass

from app.domain.research import (
    ALLOWED_CLAIM_KINDS,
    ClaimRejectionReason,
    ProposedClaim,
    RejectedClaim,
    ResearchClaim,
    ResearchPage,
)

_WHITESPACE = re.compile(r"\s+")


def _normalize_for_match(value: str) -> str:
    """Collapse whitespace and lowercase for snippet comparison.

    The model may re-wrap a sentence it copied; that is a formatting
    difference, not an invented fact. Anything beyond whitespace and case must
    still match exactly.
    """
    return _WHITESPACE.sub(" ", value).strip().lower()


@dataclass(frozen=True)
class PageContent:
    """A fetched page plus the cleaned text a snippet must be found in."""

    page: ResearchPage
    cleaned_text: str


@dataclass(frozen=True)
class ValidationOutcome:
    accepted: tuple[ResearchClaim, ...]
    rejected: tuple[RejectedClaim, ...]

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(rejection.warning for rejection in self.rejected)


class ClaimValidator:
    """Turns proposals into claims, or into recorded rejections."""

    def __init__(self, *, min_snippet_chars: int = 12) -> None:
        self._min_snippet_chars = min_snippet_chars

    def validate(
        self, proposals: tuple[ProposedClaim, ...], pages: tuple[PageContent, ...]
    ) -> ValidationOutcome:
        by_url: dict[str, PageContent] = {}
        for content in pages:
            by_url[content.page.url] = content
            by_url[content.page.final_url] = content
        normalized_text = {
            content.page.position: _normalize_for_match(content.cleaned_text)
            for content in pages
        }

        accepted: list[ResearchClaim] = []
        rejected: list[RejectedClaim] = []

        for proposal in proposals:
            rejection = self._reject_reason(proposal, by_url, normalized_text)
            if rejection is not None:
                rejected.append(rejection)
                continue
            content = by_url[proposal.source_url]
            accepted.append(
                ResearchClaim(
                    position=len(accepted),
                    kind=proposal.kind,
                    detail=proposal.detail.strip(),
                    evidence_snippet=proposal.evidence_snippet.strip(),
                    source_page_position=content.page.position,
                    confidence=proposal.confidence,
                )
            )

        return ValidationOutcome(accepted=tuple(accepted), rejected=tuple(rejected))

    def _reject_reason(
        self,
        proposal: ProposedClaim,
        by_url: dict[str, PageContent],
        normalized_text: dict[int, str],
    ) -> RejectedClaim | None:
        def reject(reason: ClaimRejectionReason, detail: str) -> RejectedClaim:
            return RejectedClaim(
                reason=reason,
                kind=proposal.kind,
                detail=proposal.detail,
                warning=f"claim rejected ({reason.value}): {detail}",
            )

        if not proposal.detail.strip() or not proposal.evidence_snippet.strip():
            return reject(ClaimRejectionReason.EMPTY_FIELD, "detail or evidence_snippet is empty")

        if proposal.kind not in ALLOWED_CLAIM_KINDS:
            return reject(
                ClaimRejectionReason.UNKNOWN_KIND, f"{proposal.kind!r} is not an allowed kind"
            )

        if not 0.0 <= proposal.confidence <= 1.0:
            return reject(
                ClaimRejectionReason.CONFIDENCE_OUT_OF_RANGE,
                f"confidence {proposal.confidence} is outside 0–1",
            )

        content = by_url.get(proposal.source_url)
        if content is None:
            return reject(
                ClaimRejectionReason.UNFETCHED_SOURCE,
                f"{proposal.source_url!r} was not fetched by this run",
            )

        if content.page.position not in normalized_text:
            return reject(
                ClaimRejectionReason.PAGE_NOT_IN_RUN,
                f"page {content.page.position} does not belong to this run",
            )

        snippet = _normalize_for_match(proposal.evidence_snippet)
        if len(snippet) < self._min_snippet_chars:
            return reject(
                ClaimRejectionReason.SNIPPET_NOT_FOUND,
                f"evidence snippet is too short to verify ({len(snippet)} chars)",
            )
        if snippet not in normalized_text[content.page.position]:
            return reject(
                ClaimRejectionReason.SNIPPET_NOT_FOUND,
                f"evidence snippet does not occur in {proposal.source_url}",
            )

        return None
