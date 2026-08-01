"""D4a persistence mappers preserve provider, evaluation and timing audit data."""

from datetime import UTC, datetime
from uuid import uuid4

from app.database.mappers.calibration import CalibrationRunMapper
from app.database.mappers.prospect_batch import ProspectBatchMapper
from app.domain.calibration import (
    CalibrationEvaluation,
    CalibrationRun,
    DraftProviderMode,
    ResearchProviderMode,
    WebsiteFetchMode,
)
from app.domain.prospect_batch import (
    ProspectBatch,
    ProspectBatchStage,
    ProspectContactType,
)

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def test_calibration_mapper_preserves_provider_modes_and_human_evaluation() -> None:
    run = CalibrationRun.create(
        discovery_task_id=uuid4(),
        prospect_batch_id=uuid4(),
        sample_count=3,
        website_fetch_mode=WebsiteFetchMode.FIXTURE,
        research_provider_mode=ResearchProviderMode.DETERMINISTIC_FAKE,
        draft_provider_mode=DraftProviderMode.DETERMINISTIC_FAKE,
    )
    evaluation = CalibrationEvaluation(
        company_id=uuid4(),
        research_accuracy=4,
        opportunity_reasonableness=3,
        contact_usability=2,
        draft_personalization=5,
        draft_professionalism=4,
        ready_for_real_outreach=False,
        reviewer_name="Mapper Reviewer",
        notes="Persist this note",
        reviewed_at=NOW,
    )
    run.record_evaluation(evaluation)

    restored = CalibrationRunMapper.to_domain(CalibrationRunMapper.to_model(run))

    assert restored.id == run.id
    assert restored.website_fetch_mode is WebsiteFetchMode.FIXTURE
    assert restored.research_provider_mode is ResearchProviderMode.DETERMINISTIC_FAKE
    assert restored.draft_provider_mode is DraftProviderMode.DETERMINISTIC_FAKE
    assert restored.evaluations == (evaluation,)


def test_prospect_batch_mapper_preserves_contact_type_and_stage_timings() -> None:
    company_id = uuid4()
    batch = ProspectBatch.create(
        discovery_task_id=uuid4(),
        requested_count=1,
        companies=((company_id, "Atlas Hardware"),),
    )
    item = batch.companies[0].move_to(ProspectBatchStage.RESEARCHING)
    item = item.with_contact(
        contact_id=uuid4(),
        name="Maria Chen",
        email="maria@example.com",
        source_url="https://example.com/contact",
        contact_type=ProspectContactType.PERSONAL,
    ).complete()
    batch.replace_company(item)
    batch.finalize()

    restored = ProspectBatchMapper.to_domain(ProspectBatchMapper.to_model(batch))
    restored_item = restored.company(company_id)

    assert restored_item.contact_type is ProspectContactType.PERSONAL
    assert [timing.stage for timing in restored_item.stage_timings] == [
        ProspectBatchStage.QUEUED,
        ProspectBatchStage.RESEARCHING,
    ]
    assert all(timing.completed_at is not None for timing in restored_item.stage_timings)
