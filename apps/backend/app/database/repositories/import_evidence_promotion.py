"""Versioned Import Evidence promotion ledger and owned signal projection."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.import_evidence import (
    ImportEvidencePromotionMapper,
    ImportEvidenceQualityMapper,
)
from app.database.models.import_evidence import (
    ImportEvidenceCompanySignalModel,
    ImportEvidencePromotionQualityAssessmentModel,
    ImportEvidenceQualityAssessmentModel,
    ImportEvidenceSignalPromotionModel,
)
from app.domain.import_evidence.models import (
    ImportEvidenceCompanySignal,
    ImportEvidenceSignalPromotion,
    PromotionStatus,
    QualityAssessment,
    SignalPromotionCandidate,
)


class SqlAlchemyImportEvidencePromotionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_quality_assessments(
        self, quality_assessment_ids: tuple[UUID, ...]
    ) -> list[QualityAssessment]:
        if not quality_assessment_ids:
            return []
        result = await self._session.execute(
            select(ImportEvidenceQualityAssessmentModel).where(
                ImportEvidenceQualityAssessmentModel.id.in_(quality_assessment_ids)
            )
        )
        return [ImportEvidenceQualityMapper.to_domain(row) for row in result.scalars()]

    async def apply_candidates(
        self, candidates: tuple[SignalPromotionCandidate, ...]
    ) -> tuple[list[ImportEvidenceSignalPromotion], bool]:
        if not candidates:
            return [], False
        company_ids = {candidate.company_id for candidate in candidates}
        if len(company_ids) != 1 or None in company_ids:
            raise ValueError("promotion batch requires one resolved company")

        existing = [await self._existing_candidate(candidate) for candidate in candidates]
        if all(row is not None for row in existing):
            rows = [row for row in existing if row is not None]
            changed = False
            for candidate, row in zip(candidates, rows, strict=True):
                if not row.is_current:
                    await self._activate_existing(candidate, row)
                    changed = True
            if changed:
                await self._session.flush()
            return [await self._promotion_domain(row) for row in rows], False
        if any(row is not None for row in existing):
            raise RuntimeError("partial promotion batch violates atomic idempotency")

        created: list[ImportEvidenceSignalPromotion] = []
        for candidate in candidates:
            created.append(await self._create_version(candidate))
        await self._session.flush()
        return created, True

    async def _existing_candidate(
        self, candidate: SignalPromotionCandidate
    ) -> ImportEvidenceSignalPromotionModel | None:
        result = await self._session.execute(
            select(ImportEvidenceSignalPromotionModel).where(
                ImportEvidenceSignalPromotionModel.aggregate_id == candidate.aggregate_id,
                ImportEvidenceSignalPromotionModel.signal_kind == candidate.signal_kind,
                ImportEvidenceSignalPromotionModel.input_fingerprint == candidate.input_fingerprint,
            )
        )
        return result.scalar_one_or_none()

    async def _activate_existing(
        self,
        candidate: SignalPromotionCandidate,
        existing: ImportEvidenceSignalPromotionModel,
    ) -> None:
        await self._supersede_current(
            company_id=existing.company_id,
            signal_kind=existing.signal_kind,
            replacement_promotion_id=existing.id,
            replacement_signal_id=existing.promoted_signal_id,
        )
        await self._session.flush()
        existing.status = (
            PromotionStatus.PROMOTED.value
            if existing.promoted_signal_id is not None
            else candidate.status.value
        )
        existing.is_current = True
        existing.superseded_by_id = None
        existing.superseded_at = None
        existing.updated_at = datetime.now(UTC)
        if existing.promoted_signal_id is not None:
            signal = await self._session.get(
                ImportEvidenceCompanySignalModel, existing.promoted_signal_id
            )
            if signal is None:
                raise RuntimeError("promotion references a missing signal projection")
            signal.is_active = True
            signal.superseded_by_id = None
            signal.superseded_at = None

    async def _create_version(
        self, candidate: SignalPromotionCandidate
    ) -> ImportEvidenceSignalPromotion:
        if candidate.company_id is None:
            raise ValueError("promotion requires company_id")
        now = datetime.now(UTC)
        promotion_id = uuid4()
        signal_id = uuid4() if candidate.status is PromotionStatus.PROMOTED else None
        if signal_id is not None and (
            candidate.quality_status is None or candidate.quality_score is None
        ):
            raise ValueError("promoted signal requires quality status and score")
        quality_status = candidate.quality_status
        quality_score = candidate.quality_score
        promotion = ImportEvidenceSignalPromotionModel(
            id=promotion_id,
            aggregate_id=candidate.aggregate_id,
            company_id=candidate.company_id,
            signal_kind=candidate.signal_kind,
            signal_detail=candidate.signal_detail,
            normalized_value_json=candidate.normalized_value_json,
            source_summary_json=candidate.source_summary_json,
            evidence_snapshot_json=candidate.evidence_snapshot_json,
            quality_status=(candidate.quality_status.value if candidate.quality_status else None),
            quality_score=candidate.quality_score,
            promotion_version=candidate.promotion_version,
            input_fingerprint=candidate.input_fingerprint,
            status=candidate.status.value,
            is_current=False,
            promoted_signal_id=signal_id,
            superseded_by_id=None,
            rejection_reasons_json=list(candidate.rejection_reasons),
            promoted_at=now if signal_id else None,
            superseded_at=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(promotion)
        # The association table has a non-deferrable parent FK. Persist the
        # stable ledger row before adding its projection and quality links.
        await self._session.flush((promotion,))
        projection: ImportEvidenceCompanySignalModel | None = None
        if signal_id is not None:
            assert quality_status is not None
            assert quality_score is not None
            projection = ImportEvidenceCompanySignalModel(
                id=signal_id,
                promotion_id=promotion_id,
                aggregate_id=candidate.aggregate_id,
                company_id=candidate.company_id,
                signal_kind=candidate.signal_kind,
                signal_detail=candidate.signal_detail,
                normalized_value_json=candidate.normalized_value_json,
                provenance_json={
                    "aggregate_id": str(candidate.aggregate_id),
                    "promotion_id": str(promotion_id),
                    "input_fingerprint": candidate.input_fingerprint,
                    "source_summary": candidate.source_summary_json,
                    "evidence_snapshot": candidate.evidence_snapshot_json,
                },
                quality_status=quality_status.value,
                quality_score=quality_score,
                ownership="import_evidence",
                is_active=False,
                superseded_by_id=None,
                created_at=now,
                superseded_at=None,
            )
            self._session.add(projection)
            await self._session.flush((projection,))

        # Replacement targets now exist, so history can safely point at them.
        # Deactivate old current rows before activating the new projection to
        # preserve the partial unique indexes throughout the transaction.
        await self._supersede_current(
            company_id=candidate.company_id,
            signal_kind=candidate.signal_kind,
            replacement_promotion_id=promotion_id,
            replacement_signal_id=signal_id,
        )
        await self._session.flush()
        promotion.is_current = True
        if projection is not None:
            projection.is_active = True
        for quality_id in candidate.quality_assessment_ids:
            self._session.add(
                ImportEvidencePromotionQualityAssessmentModel(
                    promotion_id=promotion_id,
                    quality_assessment_id=quality_id,
                    created_at=now,
                )
            )
        return replace(
            ImportEvidencePromotionMapper.promotion_to_domain(promotion),
            quality_assessment_ids=candidate.quality_assessment_ids,
        )

    async def _supersede_current(
        self,
        *,
        company_id: UUID,
        signal_kind: str,
        replacement_promotion_id: UUID,
        replacement_signal_id: UUID | None,
    ) -> None:
        result = await self._session.execute(
            select(ImportEvidenceSignalPromotionModel)
            .where(
                ImportEvidenceSignalPromotionModel.company_id == company_id,
                ImportEvidenceSignalPromotionModel.signal_kind == signal_kind,
                ImportEvidenceSignalPromotionModel.is_current.is_(True),
                ImportEvidenceSignalPromotionModel.id != replacement_promotion_id,
            )
            .with_for_update()
        )
        current = result.scalar_one_or_none()
        if current is None:
            return
        now = datetime.now(UTC)
        current.status = PromotionStatus.SUPERSEDED.value
        current.is_current = False
        current.superseded_by_id = replacement_promotion_id
        current.superseded_at = now
        current.updated_at = now
        if current.promoted_signal_id is not None:
            signal = await self._session.get(
                ImportEvidenceCompanySignalModel, current.promoted_signal_id
            )
            if signal is None:
                raise RuntimeError("current promotion has no signal projection")
            signal.is_active = False
            signal.superseded_by_id = replacement_signal_id
            signal.superseded_at = now

    async def get_promotion_by_id(self, promotion_id: UUID) -> ImportEvidenceSignalPromotion | None:
        model = await self._session.get(ImportEvidenceSignalPromotionModel, promotion_id)
        return await self._promotion_domain(model) if model else None

    async def list_current_promotions(
        self, company_id: UUID
    ) -> list[ImportEvidenceSignalPromotion]:
        result = await self._session.execute(
            select(ImportEvidenceSignalPromotionModel)
            .where(
                ImportEvidenceSignalPromotionModel.company_id == company_id,
                ImportEvidenceSignalPromotionModel.is_current.is_(True),
            )
            .order_by(ImportEvidenceSignalPromotionModel.signal_kind)
        )
        return [await self._promotion_domain(row) for row in result.scalars()]

    async def list_promotion_history(
        self, *, company_id: UUID | None = None, aggregate_id: UUID | None = None
    ) -> list[ImportEvidenceSignalPromotion]:
        statement = select(ImportEvidenceSignalPromotionModel)
        if company_id is not None:
            statement = statement.where(ImportEvidenceSignalPromotionModel.company_id == company_id)
        if aggregate_id is not None:
            statement = statement.where(
                ImportEvidenceSignalPromotionModel.aggregate_id == aggregate_id
            )
        result = await self._session.execute(
            statement.order_by(ImportEvidenceSignalPromotionModel.created_at.desc())
        )
        return [await self._promotion_domain(row) for row in result.scalars()]

    async def list_active_signals(self, company_id: UUID) -> list[ImportEvidenceCompanySignal]:
        result = await self._session.execute(
            select(ImportEvidenceCompanySignalModel)
            .where(
                ImportEvidenceCompanySignalModel.company_id == company_id,
                ImportEvidenceCompanySignalModel.is_active.is_(True),
            )
            .order_by(ImportEvidenceCompanySignalModel.signal_kind)
        )
        return [ImportEvidencePromotionMapper.signal_to_domain(row) for row in result.scalars()]

    async def _promotion_domain(
        self, model: ImportEvidenceSignalPromotionModel
    ) -> ImportEvidenceSignalPromotion:
        result = await self._session.execute(
            select(ImportEvidencePromotionQualityAssessmentModel.quality_assessment_id)
            .where(ImportEvidencePromotionQualityAssessmentModel.promotion_id == model.id)
            .order_by(ImportEvidencePromotionQualityAssessmentModel.quality_assessment_id)
        )
        return ImportEvidencePromotionMapper.promotion_to_domain(model, tuple(result.scalars()))
