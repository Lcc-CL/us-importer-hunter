"""Synchronous single-company CSV evidence-to-draft orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import TracebackType
from typing import Protocol
from uuid import UUID, uuid4

from app.domain.events import CompanyFactsChanged
from app.domain.import_evidence.models import (
    ImportEvidenceSignalPromotion,
    PromotionStatus,
    QualityAssessment,
    QualityStatus,
)
from app.domain.import_evidence.values import (
    EntityMatchMethod,
    EntityMatchStatus,
    ImporterEntityMatch,
)
from app.domain.repositories import (
    CompanyRepository,
    ContactRepository,
    ImportEvidencePromotionRepository,
    ImportEvidenceRepository,
    OpportunityRepository,
    OutreachRepository,
)
from app.domain.services import SenderProfile
from app.services.import_evidence.aggregate import AggregateShipmentInput
from app.services.import_evidence.entity_resolver import (
    DeterministicEntityResolver,
    ResolutionResult,
    normalize_domain,
)
from app.services.import_evidence.quality import EvidenceQualityScorer
from app.services.import_evidence.upload import ParsedEvidenceRow, parse_company_csv
from app.shared.normalization import normalize_company_name
from app.workflows.decision_maker import (
    DecisionMakerSelectionAction,
    DecisionMakerSelectionWorkflow,
)
from app.workflows.email import EmailDraftGenerationWorkflow
from app.workflows.import_evidence.promotion import ImportEvidenceSignalPromotionWorkflow
from app.workflows.import_evidence.workflow import (
    ImportEvidenceAggregateRequest,
    ImportEvidenceClosureWorkflow,
)
from app.workflows.mvp_prospect_analysis import MVP_SYSTEM_USER_ID
from app.workflows.opportunity import OpportunityApplicationWorkflow


class EvidenceFlowUnitOfWork(Protocol):
    companies: CompanyRepository
    contacts: ContactRepository
    import_evidence: ImportEvidenceRepository
    import_evidence_promotions: ImportEvidencePromotionRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository

    async def __aenter__(self) -> "EvidenceFlowUnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class EvidenceFlowStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class EvidenceUploadOutcome:
    status: EvidenceFlowStatus
    company_id: UUID
    import_job_id: UUID | None = None
    aggregate_id: UUID | None = None
    records_received: int = 0
    records_normalized: int = 0
    shipments_matched: int = 0
    quality_status: str | None = None
    quality_score: float | None = None
    promoted_signals: tuple[str, ...] = ()
    previous_qualification_score: float | None = None
    qualification_score: float | None = None
    qualification_status: str | None = None
    qualification_reasons: tuple[str, ...] = ()
    draft_status: str = "skipped"
    warnings: tuple[str, ...] = ()


class EvidenceUploadError(ValueError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class EvidenceToDraftWorkflow:
    def __init__(
        self,
        uow_factory: Callable[[], EvidenceFlowUnitOfWork],
        opportunity: OpportunityApplicationWorkflow,
        decision_maker: DecisionMakerSelectionWorkflow,
        email_draft: EmailDraftGenerationWorkflow,
    ) -> None:
        self._uow_factory = uow_factory
        self._closure = ImportEvidenceClosureWorkflow(uow_factory)
        self._promotion = ImportEvidenceSignalPromotionWorkflow(uow_factory)
        self._opportunity = opportunity
        self._decision_maker = decision_maker
        self._email_draft = email_draft
        self._resolver = DeterministicEntityResolver()
        self._quality = EvidenceQualityScorer()

    async def upload(
        self,
        *,
        company_id: UUID,
        content: bytes,
        provider_name: str = "csv",
        as_of_date: date | None = None,
        sender: SenderProfile | None = None,
    ) -> EvidenceUploadOutcome:
        reference_date = as_of_date or date.today()
        request_id = uuid4()
        async with self._uow_factory() as uow:
            company = await uow.companies.get_by_id(company_id)
            if company is None:
                raise EvidenceUploadError("company", "公司不存在")
            previous = await uow.opportunities.get_for_company_and_user(
                company_id, MVP_SYSTEM_USER_ID
            )
            previous_score = previous.score.value if previous and previous.score else None
            company_name = company.name.value
            company_domain = company.website.host if company.website else ""

        try:
            parsed = await parse_company_csv(
                content,
                company_name=company_name,
                provider_name=provider_name,
                request_id=request_id,
            )
        except ValueError as exc:
            raise EvidenceUploadError("csv_parse", str(exc)) from exc

        async with self._uow_factory() as uow:
            job_id = await uow.import_evidence.create_upload_job(
                company_id, provider_name, request_id
            )
            persisted: list[tuple[ParsedEvidenceRow, UUID, ResolutionResult]] = []
            created_shipments = 0
            for row in parsed.rows:
                raw_id = await uow.import_evidence.save_upload_record(job_id, row.raw_record)
                shipment_id, created = await uow.import_evidence.save_normalized_shipment(
                    job_id, row.shipment, raw_id
                )
                created_shipments += int(created)
                resolution = self._resolve(
                    row,
                    company_name=company_name,
                    company_domain=company_domain,
                )
                match = ImporterEntityMatch(
                    company_id=(
                        company_id
                        if resolution.match_status is EntityMatchStatus.AUTO_MATCH
                        else None
                    ),
                    normalized_name=normalize_company_name(row.shipment.importer_name),
                    match_method=resolution.match_method,
                    match_score=resolution.match_score,
                    match_reasons=resolution.match_reasons,
                    candidate_company_ids=(company_id,),
                    review_status=resolution.match_status,
                )
                await uow.import_evidence.save_entity_match(shipment_id, match)
                persisted.append((row, shipment_id, resolution))
            await uow.commit()

        matched = [
            item for item in persisted if item[2].match_status is EntityMatchStatus.AUTO_MATCH
        ]
        warnings = list(parsed.warnings)
        if len(matched) != len(persisted):
            warnings.append(f"{len(persisted) - len(matched)} 票记录需要人工确认")
        if not matched:
            await self._finish_job(
                job_id,
                status="needs_review",
                records_received=parsed.records_received,
                records_normalized=len(persisted),
                created_shipments=created_shipments,
                matched=0,
                promoted=0,
                error_message="没有可自动匹配到当前公司的 Shipment",
            )
            return EvidenceUploadOutcome(
                status=EvidenceFlowStatus.NEEDS_REVIEW,
                company_id=company_id,
                import_job_id=job_id,
                records_received=parsed.records_received,
                records_normalized=len(persisted),
                previous_qualification_score=previous_score,
                qualification_score=previous_score,
                qualification_status=(
                    previous.history[-1].qualification_decision.value
                    if previous and previous.history and previous.history[-1].qualification_decision
                    else None
                ),
                warnings=tuple((*warnings, "未生成 Aggregate 或 Signal")),
            )

        aggregate_inputs: list[AggregateShipmentInput] = []
        qualities = []
        for row, shipment_id, resolution in matched:
            arrival_date = row.shipment.arrival_date.date() if row.shipment.arrival_date else None
            assessment = self._quality.assess(
                provider_names=(provider_name,),
                normalized_shipment_id=shipment_id,
                shipment_fingerprint=row.shipment.shipment_fingerprint,
                entity_match_status=resolution.match_status.value,
                has_house_bol=bool(row.shipment.house_bol),
                has_master_bol=bool(row.shipment.master_bol),
                has_importer=bool(row.shipment.importer_name),
                has_arrival_date=arrival_date is not None,
                has_carrier_scac=bool(row.shipment.carrier_scac),
                has_containers=bool(row.shipment.container_numbers),
                cross_source_agreement=1.0,
                arrival_date_value=arrival_date,
                now=reference_date,
            )
            persisted_quality = await self._closure.persist_quality(assessment)
            quality = persisted_quality.assessment
            qualities.append(quality)
            aggregate_inputs.append(
                AggregateShipmentInput(
                    normalized_shipment_id=shipment_id,
                    shipment_fingerprint=row.shipment.shipment_fingerprint,
                    quality_assessment_id=quality.id,
                    quality_fingerprint=quality.input_fingerprint,
                    quality_status=quality.quality_status.value,
                    quality_hard_blockers=quality.hard_blockers,
                    dedupe_status=row.shipment.dedupe_status,
                    entity_match_status=resolution.match_status.value,
                    importer_identity=row.shipment.importer_name,
                    arrival_date=arrival_date,
                    origin=row.shipment.country_of_origin,
                    supplier=row.shipment.shipper_name,
                    containers=row.shipment.container_numbers,
                    weight_kg=row.shipment.weight_kg,
                    carrier=row.shipment.carrier_scac,
                    port=row.shipment.port_of_discharge,
                    source_provider_count=1,
                    source_providers=(provider_name,),
                )
            )

        aggregate_result = await self._closure.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity=company_name,
                company_id=company_id,
                shipments=tuple(aggregate_inputs),
                as_of_date=reference_date,
            )
        )
        promotion = await self._promotion.promote(aggregate_result.aggregate.id)
        promoted = tuple(
            row.signal_kind
            for row in promotion.promotions
            if row.status is PromotionStatus.PROMOTED
        )
        await self._finish_job(
            job_id,
            status="partial" if warnings else "completed",
            records_received=parsed.records_received,
            records_normalized=len(persisted),
            created_shipments=created_shipments,
            matched=len(matched),
            promoted=len(promoted),
        )

        qualification = await self._opportunity.handle(
            CompanyFactsChanged(
                company_id=company_id,
                changed_fields=("import_evidence_signals",),
                reason="CSV Import Evidence upload completed",
            ),
            user_id=MVP_SYSTEM_USER_ID,
        )
        draft_status = "skipped"
        if qualification.qualification_decision == "qualified" and qualification.opportunity_id:
            selection = await self._decision_maker.handle(
                company_id=company_id,
                opportunity_id=qualification.opportunity_id,
            )
            if selection.action is DecisionMakerSelectionAction.SELECTED and sender is not None:
                assert selection.selected_contact_id is not None
                draft = await self._email_draft.handle(
                    opportunity_id=qualification.opportunity_id,
                    contact_id=selection.selected_contact_id,
                    sender=sender,
                )
                draft_status = draft.action.value
            elif sender is None:
                warnings.append("发件人资料缺失，未生成 Draft")
            else:
                warnings.append("没有可自动选择的决策人，未生成 Draft")
        elif qualification.qualification_decision != "qualified":
            warnings.append("Qualification 未达标，未生成 Draft")

        quality_status, quality_score = self._quality_summary(qualities)
        return EvidenceUploadOutcome(
            status=EvidenceFlowStatus.PARTIAL if warnings else EvidenceFlowStatus.COMPLETED,
            company_id=company_id,
            import_job_id=job_id,
            aggregate_id=aggregate_result.aggregate.id,
            records_received=parsed.records_received,
            records_normalized=len(persisted),
            shipments_matched=len(matched),
            quality_status=quality_status,
            quality_score=quality_score,
            promoted_signals=promoted,
            previous_qualification_score=previous_score,
            qualification_score=qualification.score,
            qualification_status=qualification.qualification_decision,
            qualification_reasons=qualification.reasons,
            draft_status=draft_status,
            warnings=tuple(warnings),
        )

    async def get_current(self, company_id: UUID) -> EvidenceUploadOutcome | None:
        async with self._uow_factory() as uow:
            company = await uow.companies.get_by_id(company_id)
            if company is None:
                raise EvidenceUploadError("company", "公司不存在")
            job = await uow.import_evidence.get_latest_upload_job(company_id)
            aggregate = await uow.import_evidence.get_current_aggregate_for_company(company_id)
            if job is None or aggregate is None:
                return None
            promotions = await uow.import_evidence_promotions.list_current_promotions(company_id)
            opportunity = await uow.opportunities.get_for_company_and_user(
                company_id, MVP_SYSTEM_USER_ID
            )
            current_assessment = (
                opportunity.history[-1] if opportunity and opportunity.history else None
            )
            draft_status = "skipped"
            if opportunity is not None:
                outreaches = await uow.outreaches.list_for_opportunity(opportunity.id)
                drafts = [draft for outreach in outreaches for draft in outreach.drafts]
                if drafts:
                    draft_status = max(drafts, key=lambda row: row.generated_at).status.value
        quality_rows = [row for row in promotions if row.quality_status is not None]
        quality_status = self._promotion_quality_status(quality_rows)
        quality_score = min(
            (row.quality_score for row in quality_rows if row.quality_score is not None),
            default=None,
        )
        return EvidenceUploadOutcome(
            status=EvidenceFlowStatus(job[1]),
            company_id=company_id,
            import_job_id=job[0],
            aggregate_id=aggregate.id,
            records_received=job[2],
            records_normalized=job[3],
            shipments_matched=job[5],
            quality_status=quality_status,
            quality_score=quality_score,
            promoted_signals=tuple(
                row.signal_kind for row in promotions if row.status is PromotionStatus.PROMOTED
            ),
            qualification_score=(
                current_assessment.new_score.value if current_assessment else None
            ),
            qualification_status=(
                current_assessment.qualification_decision.value
                if current_assessment and current_assessment.qualification_decision
                else None
            ),
            qualification_reasons=current_assessment.reasons if current_assessment else (),
            draft_status=draft_status,
        )

    def _resolve(
        self,
        row: ParsedEvidenceRow,
        *,
        company_name: str,
        company_domain: str,
    ) -> ResolutionResult:
        resolution = self._resolver.resolve(
            row.shipment.importer_name,
            shipment_domain=row.importer_domain,
            shipment_country=row.importer_country,
            shipment_role="importer",
            candidate_name=company_name,
            candidate_domain=company_domain,
            candidate_country=row.importer_country,
        )
        exact_name = normalize_company_name(row.shipment.importer_name) == normalize_company_name(
            company_name
        )
        exact_domain = bool(row.importer_domain and company_domain) and normalize_domain(
            row.importer_domain
        ) == normalize_domain(company_domain)
        if exact_name and exact_domain:
            return ResolutionResult(
                match_status=EntityMatchStatus.AUTO_MATCH,
                match_score=95.0,
                match_method=EntityMatchMethod.STRONG,
                match_reasons=("targeted_upload:exact_name_and_domain",),
                positive_evidence=("exact_name_match", "domain_match"),
            )
        return resolution

    async def _finish_job(
        self,
        job_id: UUID,
        *,
        status: str,
        records_received: int,
        records_normalized: int,
        created_shipments: int,
        matched: int,
        promoted: int,
        error_message: str | None = None,
    ) -> None:
        async with self._uow_factory() as uow:
            await uow.import_evidence.finish_upload_job(
                job_id,
                status=status,
                total_raw=records_received,
                total_normalized=records_normalized,
                total_deduped=created_shipments,
                total_matched=matched,
                total_promoted=promoted,
                error_message=error_message,
            )
            await uow.commit()

    @staticmethod
    def _quality_summary(
        qualities: list[QualityAssessment],
    ) -> tuple[str | None, float | None]:
        if not qualities:
            return None, None
        rank = {
            QualityStatus.VERIFIED: 0,
            QualityStatus.USABLE: 1,
            QualityStatus.REVIEW: 2,
            QualityStatus.REJECTED: 3,
        }
        worst = max(qualities, key=lambda row: rank[row.quality_status])
        return worst.quality_status.value, min(row.total_score for row in qualities)

    @staticmethod
    def _promotion_quality_status(
        rows: list[ImportEvidenceSignalPromotion],
    ) -> str | None:
        statuses = [row.quality_status for row in rows if row.quality_status is not None]
        if not statuses:
            return None
        rank = {QualityStatus.VERIFIED: 0, QualityStatus.USABLE: 1}
        return max(statuses, key=lambda value: rank.get(value, 99)).value
