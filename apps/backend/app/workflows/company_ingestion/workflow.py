"""Company ingestion workflow: CompanyDiscovered claim → canonical Company.

The application-layer consumer of Discovery's events (ADR-0019):

    CompanyDiscovered
        → normalize (SnapshotNormalizer: raw text → CompanyName/WebsiteUrl)
        → deduplicate (RepositoryCompanyDeduplicator: name, then host)
        → create Company | merge into existing (alias / source / signal / website)
        → commit (one Unit of Work per event)

Discovery still knows nothing about Company — this workflow is the only
place the two sides meet. No real data sources are called here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.company import Company
from app.domain.events import CompanyDiscovered, CompanyIngested
from app.domain.exceptions import DomainError, DuplicateOperation, InvalidCompanyName
from app.domain.repositories import UnitOfWork
from app.domain.values import CompanyName
from app.services.company import (
    NormalizedClaim,
    RepositoryCompanyDeduplicator,
    SnapshotNormalizer,
)


class IngestionStatus(StrEnum):
    CREATED = "created"
    MERGED = "merged"
    REJECTED = "rejected"


@dataclass(frozen=True)
class IngestionOutcome:
    status: IngestionStatus
    company_id: UUID | None
    notes: tuple[str, ...] = ()
    event: CompanyIngested | None = None  # for the opportunity workflow (no bus yet)


class CompanyIngestionWorkflow:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        normalizer: SnapshotNormalizer | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._normalizer = normalizer or SnapshotNormalizer()

    async def handle(self, event: CompanyDiscovered) -> IngestionOutcome:
        snapshot = event.result.snapshot
        try:
            claim = self._normalizer.normalize(snapshot)
        except InvalidCompanyName as exc:
            return IngestionOutcome(
                status=IngestionStatus.REJECTED,
                company_id=None,
                notes=(f"unusable company name: {exc}",),
            )

        notes: list[str] = []
        if claim.website_dropped:
            notes.append(f"website text dropped as invalid: {snapshot.website_text!r}")

        async with self._uow_factory() as uow:
            deduplicator = RepositoryCompanyDeduplicator(uow.companies)
            canonical_id = await deduplicator.find_canonical(claim.name, claim.website)

            if canonical_id is None:
                company = Company.create(claim.name, claim.website)
                self._apply_claim_facts(company, event, notes)
                await uow.companies.add(company)
                status = IngestionStatus.CREATED
            else:
                existing = await uow.companies.get_by_id(canonical_id)
                assert existing is not None, "deduplicator returned a vanished company id"
                company = existing
                self._merge_claim(company, claim, event, notes)
                await uow.companies.save(company)
                status = IngestionStatus.MERGED

            await uow.commit()
            return IngestionOutcome(
                status=status,
                company_id=company.id,
                notes=tuple(notes),
                event=CompanyIngested(
                    company_id=company.id,
                    ingestion_result="created" if status is IngestionStatus.CREATED else "merged",
                    source=event.result.snapshot.source.source,
                ),
            )

    # -- merge policy ---------------------------------------------------

    def _merge_claim(
        self,
        company: Company,
        claim: NormalizedClaim,
        event: CompanyDiscovered,
        notes: list[str],
    ) -> None:
        if claim.name.normalized != company.name.normalized:
            try:
                company.add_alias(CompanyName(claim.name.value))
                notes.append(f"alias recorded: {claim.name.value!r}")
            except DuplicateOperation:
                pass  # alias already known — merge stays idempotent
        if claim.website is not None:
            try:
                company.set_website(claim.website)
            except DomainError as exc:
                notes.append(f"website kept unchanged: {exc}")
        self._apply_claim_facts(company, event, notes)

    def _apply_claim_facts(
        self, company: Company, event: CompanyDiscovered, notes: list[str]
    ) -> None:
        source = event.result.snapshot.source
        already_recorded = any(
            ref.source == source.source and ref.reference == source.reference
            for ref in company.sources
        )
        if already_recorded:
            notes.append("source already recorded — skipped")
        else:
            company.add_source(source)
        for signal in event.result.signals:
            company.add_signal(f"{signal.kind}: {signal.detail}")
