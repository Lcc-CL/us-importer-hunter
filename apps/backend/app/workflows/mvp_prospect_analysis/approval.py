"""Application workflow for human approval of a generated email draft."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.exceptions import DomainError, DuplicateOperation, InvalidStateTransition
from app.shared.exceptions import ApplicationConflictError, ResourceNotFoundError
from app.workflows.mvp_prospect_analysis.workflow import UowFactory


@dataclass(frozen=True)
class DraftApprovalOutcome:
    outreach_id: UUID
    version: int
    approval_status: str
    approved_at: datetime
    approved_by_name: str

    @property
    def status(self) -> str:
        """Backward-compatible API alias."""
        return self.approval_status

    @property
    def approved_by(self) -> str:
        """Backward-compatible API alias."""
        return self.approved_by_name


class ApproveEmailDraftWorkflow:
    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(
        self,
        *,
        outreach_id: UUID,
        version: int,
        approver_id: UUID | None,
        approver_name: str | None,
    ) -> DraftApprovalOutcome:
        approved_by_name = (approver_name or "").strip()
        if not approved_by_name and approver_id is not None:
            # Compatibility for the original approver_id-only request contract.
            approved_by_name = str(approver_id)
        async with self._uow_factory() as uow:
            outreach = await uow.outreaches.get_by_id(outreach_id)
            if outreach is None:
                raise ResourceNotFoundError(f"outreach {outreach_id} was not found")
            if not any(draft.version == version for draft in outreach.drafts):
                raise ResourceNotFoundError(
                    f"draft version {version} was not found on outreach {outreach_id}"
                )
            try:
                outreach.approve_draft(version, approved_by_name=approved_by_name)
                await uow.outreaches.save(outreach)
                await uow.commit()
            except (InvalidStateTransition, DuplicateOperation) as exc:
                raise ApplicationConflictError(str(exc)) from exc
            except DomainError as exc:
                raise ApplicationConflictError(str(exc)) from exc

            outreach.drain_events()
            draft = next(item for item in outreach.drafts if item.version == version)
            assert draft.approved_at is not None
            assert draft.approved_by_name is not None
            return DraftApprovalOutcome(
                outreach_id=outreach.id,
                version=version,
                approval_status=draft.approval_status.value,
                approved_at=draft.approved_at,
                approved_by_name=draft.approved_by_name,
            )
