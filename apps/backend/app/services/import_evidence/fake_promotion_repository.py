"""In-memory promotion repository with PostgreSQL-equivalent lifecycle rules."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.import_evidence.models import (
    ImportEvidenceCompanySignal,
    ImportEvidenceSignalPromotion,
    PromotionStatus,
    QualityAssessment,
    SignalPromotionCandidate,
)


class FakeImportEvidencePromotionRepository:
    def __init__(self, quality_assessments: tuple[QualityAssessment, ...] = ()) -> None:
        self.qualities = {row.id: row for row in quality_assessments}
        self.promotions: dict[UUID, ImportEvidenceSignalPromotion] = {}
        self.signals: dict[UUID, ImportEvidenceCompanySignal] = {}

    async def get_quality_assessments(
        self, quality_assessment_ids: tuple[UUID, ...]
    ) -> list[QualityAssessment]:
        return [
            self.qualities[row_id] for row_id in quality_assessment_ids if row_id in self.qualities
        ]

    async def apply_candidates(
        self, candidates: tuple[SignalPromotionCandidate, ...]
    ) -> tuple[list[ImportEvidenceSignalPromotion], bool]:
        existing = [self._find_candidate(candidate) for candidate in candidates]
        if all(row is not None for row in existing):
            rows = [row for row in existing if row is not None]
            for candidate, row in zip(candidates, rows, strict=True):
                if not row.is_current:
                    self._supersede_current(
                        row.company_id, row.signal_kind, row.id, row.promoted_signal_id
                    )
                    status = (
                        PromotionStatus.PROMOTED if row.promoted_signal_id else candidate.status
                    )
                    self.promotions[row.id] = replace(
                        row,
                        status=status,
                        is_current=True,
                        superseded_by_id=None,
                        superseded_at=None,
                    )
                    if row.promoted_signal_id:
                        signal = self.signals[row.promoted_signal_id]
                        self.signals[signal.id] = replace(
                            signal,
                            is_active=True,
                            superseded_by_id=None,
                            superseded_at=None,
                        )
            return [self.promotions[row.id] for row in rows], False
        if any(row is not None for row in existing):
            raise RuntimeError("partial promotion batch violates atomic idempotency")

        rows = [self._create(candidate) for candidate in candidates]
        return rows, bool(rows)

    def _find_candidate(
        self, candidate: SignalPromotionCandidate
    ) -> ImportEvidenceSignalPromotion | None:
        return next(
            (
                row
                for row in self.promotions.values()
                if row.aggregate_id == candidate.aggregate_id
                and row.signal_kind == candidate.signal_kind
                and row.input_fingerprint == candidate.input_fingerprint
            ),
            None,
        )

    def _create(self, candidate: SignalPromotionCandidate) -> ImportEvidenceSignalPromotion:
        if candidate.company_id is None:
            raise ValueError("promotion requires company_id")
        now = datetime.now(UTC)
        promotion_id = uuid4()
        signal_id = uuid4() if candidate.status is PromotionStatus.PROMOTED else None
        self._supersede_current(
            candidate.company_id, candidate.signal_kind, promotion_id, signal_id
        )
        promotion = ImportEvidenceSignalPromotion(
            id=promotion_id,
            aggregate_id=candidate.aggregate_id,
            company_id=candidate.company_id,
            signal_kind=candidate.signal_kind,
            signal_detail=candidate.signal_detail,
            normalized_value_json=candidate.normalized_value_json,
            source_summary_json=candidate.source_summary_json,
            evidence_snapshot_json=candidate.evidence_snapshot_json,
            quality_status=candidate.quality_status,
            quality_score=candidate.quality_score,
            promotion_version=candidate.promotion_version,
            input_fingerprint=candidate.input_fingerprint,
            status=candidate.status,
            promoted_signal_id=signal_id,
            quality_assessment_ids=candidate.quality_assessment_ids,
            rejection_reasons=candidate.rejection_reasons,
            promoted_at=now if signal_id else None,
            created_at=now,
            updated_at=now,
        )
        self.promotions[promotion_id] = promotion
        if signal_id is not None:
            if candidate.quality_status is None or candidate.quality_score is None:
                raise ValueError("promoted signal requires quality")
            self.signals[signal_id] = ImportEvidenceCompanySignal(
                id=signal_id,
                promotion_id=promotion_id,
                aggregate_id=candidate.aggregate_id,
                company_id=candidate.company_id,
                signal_kind=candidate.signal_kind,
                signal_detail=candidate.signal_detail,
                normalized_value_json=candidate.normalized_value_json,
                provenance_json={"aggregate_id": str(candidate.aggregate_id)},
                quality_status=candidate.quality_status,
                quality_score=candidate.quality_score,
                created_at=now,
            )
        return promotion

    def _supersede_current(
        self,
        company_id: UUID | None,
        kind: str,
        replacement_promotion_id: UUID,
        replacement_signal_id: UUID | None,
    ) -> None:
        now = datetime.now(UTC)
        for row in tuple(self.promotions.values()):
            if (
                row.company_id == company_id
                and row.signal_kind == kind
                and row.is_current
                and row.id != replacement_promotion_id
            ):
                self.promotions[row.id] = replace(
                    row,
                    status=PromotionStatus.SUPERSEDED,
                    is_current=False,
                    superseded_by_id=replacement_promotion_id,
                    superseded_at=now,
                    updated_at=now,
                )
                if row.promoted_signal_id:
                    signal = self.signals[row.promoted_signal_id]
                    self.signals[signal.id] = replace(
                        signal,
                        is_active=False,
                        superseded_by_id=replacement_signal_id,
                        superseded_at=now,
                    )

    async def get_promotion_by_id(self, promotion_id: UUID) -> ImportEvidenceSignalPromotion | None:
        return self.promotions.get(promotion_id)

    async def list_current_promotions(
        self, company_id: UUID
    ) -> list[ImportEvidenceSignalPromotion]:
        return sorted(
            (
                row
                for row in self.promotions.values()
                if row.company_id == company_id and row.is_current
            ),
            key=lambda row: row.signal_kind,
        )

    async def list_promotion_history(
        self, *, company_id: UUID | None = None, aggregate_id: UUID | None = None
    ) -> list[ImportEvidenceSignalPromotion]:
        rows = [
            row
            for row in self.promotions.values()
            if (company_id is None or row.company_id == company_id)
            and (aggregate_id is None or row.aggregate_id == aggregate_id)
        ]
        return sorted(rows, key=lambda row: row.created_at, reverse=True)

    async def list_active_signals(self, company_id: UUID) -> list[ImportEvidenceCompanySignal]:
        return sorted(
            (
                row
                for row in self.signals.values()
                if row.company_id == company_id and row.is_active
            ),
            key=lambda row: row.signal_kind,
        )
