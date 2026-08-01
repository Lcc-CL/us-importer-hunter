"""D4a calibration aggregate invariants."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.calibration import (
    CalibrationEvaluation,
    CalibrationRun,
    DraftProviderMode,
    ResearchProviderMode,
    WebsiteFetchMode,
)
from app.domain.exceptions import DomainError

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def make_run(*, sample_count: int = 3) -> CalibrationRun:
    return CalibrationRun.create(
        discovery_task_id=uuid4(),
        prospect_batch_id=uuid4(),
        sample_count=sample_count,
        website_fetch_mode=WebsiteFetchMode.FIXTURE,
        research_provider_mode=ResearchProviderMode.DETERMINISTIC_FAKE,
        draft_provider_mode=DraftProviderMode.DETERMINISTIC_FAKE,
    )


@pytest.mark.parametrize("sample_count", [2, 6])
def test_calibration_requires_three_to_five_companies(sample_count: int) -> None:
    with pytest.raises(DomainError, match="between 3 and 5"):
        make_run(sample_count=sample_count)


def test_human_evaluation_is_trimmed_validated_and_replaced_per_company() -> None:
    run = make_run()
    company_id = uuid4()
    first = CalibrationEvaluation(
        company_id=company_id,
        research_accuracy=3,
        opportunity_reasonableness=3,
        contact_usability=2,
        draft_personalization=4,
        draft_professionalism=4,
        ready_for_real_outreach=False,
        reviewer_name="  Internal Reviewer  ",
        notes="  needs a stronger contact  ",
        reviewed_at=NOW,
    )
    replacement = CalibrationEvaluation(
        company_id=company_id,
        research_accuracy=4,
        opportunity_reasonableness=4,
        contact_usability=3,
        draft_personalization=5,
        draft_professionalism=5,
        ready_for_real_outreach=True,
        reviewer_name="Internal Reviewer",
        notes=None,
        reviewed_at=NOW,
    )

    run.record_evaluation(first)
    run.record_evaluation(replacement)

    assert run.evaluations == (replacement,)
    assert first.reviewer_name == "Internal Reviewer"
    assert first.notes == "needs a stronger contact"


@pytest.mark.parametrize("score", [0, 6])
def test_human_evaluation_scores_are_one_to_five(score: int) -> None:
    with pytest.raises(DomainError, match="between 1 and 5"):
        CalibrationEvaluation(
            company_id=uuid4(),
            research_accuracy=score,
            opportunity_reasonableness=3,
            contact_usability=3,
            draft_personalization=3,
            draft_professionalism=3,
            ready_for_real_outreach=False,
            reviewer_name="Reviewer",
            notes=None,
            reviewed_at=NOW,
        )
