"""Candidate selection: from scored contacts to Primary / Alternatives /
Supporting / Rejected.

Selection is a pure function of scored candidates — no I/O, no side effects.
Thresholds and tie-breaking rules live here so the whole decision is in one
place.
"""

from collections.abc import Sequence

from app.domain.contact import SelectionThresholds
from app.services.contact.scorer import (
    CandidateScore,
    DecisionMakerSelectionResult,
    RejectionReason,
    SelectionStatus,
)

SELECT_SCORE = 55.0
REVIEW_SCORE = 35.0
CLOSE_MARGIN = 5.0
REACHABILITY_TIE_MARGIN = 3.0
MAX_ALTERNATIVES = 3


def select(
    candidates: Sequence[CandidateScore],
    *,
    thresholds: SelectionThresholds | None = None,
) -> DecisionMakerSelectionResult:
    thresholds = thresholds or SelectionThresholds()
    select_bar = thresholds.select_score
    review_bar = thresholds.review_score

    eligible = [c for c in candidates if c.eligible]
    rejected = [c for c in candidates if not c.eligible]

    if not eligible and not rejected:
        return _empty(SelectionStatus.NO_RELEVANT_CONTACT, ("no contacts available",))

    if not eligible:
        return DecisionMakerSelectionResult(
            status=SelectionStatus.NO_RELEVANT_CONTACT,
            review_required=False,
            review_reasons=("no eligible candidates — all rejected",),
            primary_contact=None,
            alternative_contacts=(),
            supporting_contacts=(),
            rejected_contacts=tuple(_tag_rejected(rejected)),
        )

    ranked = sorted(eligible, key=_rank_key)

    if all(
        c.overall_score < review_bar for c in ranked
    ):
        result = DecisionMakerSelectionResult(
            status=SelectionStatus.NO_RELEVANT_CONTACT,
            review_required=False,
            review_reasons=("no candidate meets the minimum review bar",),
            primary_contact=None,
            alternative_contacts=(),
            supporting_contacts=(),
            rejected_contacts=tuple(
                list(_tag_rejected(rejected))
                + list(
                    _as_rejected(c, RejectionReason.INSUFFICIENT_ROLE_FIT)
                    for c in ranked
                )
            ),
        )
        return result

    best = ranked[0]
    second = ranked[1] if len(ranked) >= 2 else None

    review: list[str] = []
    review_needed = False

    if best.overall_score < select_bar:
        review_needed = True
        review.append(
            f"best candidate score {best.overall_score} below selection bar {select_bar}"
        )

    if second and (best.overall_score - second.overall_score) <= CLOSE_MARGIN:
        review_needed = True
        review.append(
            f"top two candidates within {CLOSE_MARGIN} points "
            f"({best.overall_score} vs {second.overall_score})"
        )

    best_reach = best.reachability_score
    if best_reach == 0:
        review_needed = True
        review.append("best candidate has no reachable channel")
    elif (
        second
        and best.role_relevance_score > second.role_relevance_score
        and best_reach == 0
        and second.reachability_score > 0
        and (best.overall_score - second.overall_score) <= REACHABILITY_TIE_MARGIN
    ):
        review_needed = True
        review.append(
            "best candidate has higher role relevance but is unreachable; "
            "second candidate is reachable within tie margin"
        )

    if best.role_classification_confidence < 0.6:
        review_needed = True
        review.append(
            f"primary classification confidence {best.role_classification_confidence} < 0.6"
        )

    if review_needed:
        primary = None
        alternatives = tuple(
            _tagged(c, SelectionStatus.ALTERNATIVES_AVAILABLE)
            for c in ranked[:MAX_ALTERNATIVES]
        )
        return DecisionMakerSelectionResult(
            status=SelectionStatus.REVIEW_REQUIRED,
            review_required=True,
            review_reasons=tuple(review),
            primary_contact=None,
            alternative_contacts=alternatives,
            supporting_contacts=_supporting(ranked, MAX_ALTERNATIVES),
            rejected_contacts=tuple(_tag_rejected(rejected)),
        )

    primary = _tagged(best, SelectionStatus.SELECTED)
    alts_start = 1
    alternatives = tuple(
        _tagged(c, SelectionStatus.ALTERNATIVES_AVAILABLE)
        for c in ranked[alts_start : alts_start + MAX_ALTERNATIVES]
    )

    return DecisionMakerSelectionResult(
        status=(
            SelectionStatus.SELECTED
            if best.overall_score >= select_bar
            else SelectionStatus.ALTERNATIVES_AVAILABLE
        ),
        review_required=False,
        review_reasons=(),
        primary_contact=primary,
        alternative_contacts=alternatives,
        supporting_contacts=_supporting(ranked, alts_start + MAX_ALTERNATIVES),
        rejected_contacts=tuple(_tag_rejected(rejected)),
    )


def _empty(status: SelectionStatus, reasons: tuple[str, ...]) -> DecisionMakerSelectionResult:
    return DecisionMakerSelectionResult(
        status=status,
        review_required=False,
        review_reasons=reasons,
        primary_contact=None,
        alternative_contacts=(),
        supporting_contacts=(),
        rejected_contacts=(),
    )


def _tagged(candidate: CandidateScore, status: SelectionStatus) -> CandidateScore:
    from dataclasses import replace

    return replace(candidate, selection_status=status)


def _as_rejected(candidate: CandidateScore, reason: RejectionReason) -> CandidateScore:
    from dataclasses import replace

    return replace(
        candidate,
        eligible=False,
        selection_status=SelectionStatus.NO_RELEVANT_CONTACT,
        rejection_reasons=candidate.rejection_reasons + (reason,),
    )


def _tag_rejected(candidates: list[CandidateScore]) -> list[CandidateScore]:
    from dataclasses import replace

    return [
        replace(c, selection_status=SelectionStatus.NO_RELEVANT_CONTACT) for c in candidates
    ]


def _supporting(
    ranked: list[CandidateScore], after: int
) -> tuple[CandidateScore, ...]:
    result: list[CandidateScore] = []
    for c in ranked[after:]:
        if c.reachability_score == 0 or c.assistant_role:
            result.append(
                _tagged(c, SelectionStatus.ALTERNATIVES_AVAILABLE)
            )
    return tuple(result)


def _rank_key(candidate: CandidateScore) -> tuple[float, float, float, float, float, str]:
    return (
        -candidate.overall_score,
        -candidate.role_relevance_score,
        -candidate.seniority_score,
        -candidate.reachability_score,
        -candidate.source_confidence_score,
        str(candidate.contact_id),
    )
