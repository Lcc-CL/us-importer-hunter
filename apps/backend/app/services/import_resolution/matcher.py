"""Deterministic company and contact identity matching policy."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

from app.domain.import_resolution import (
    CompanyResolutionCandidate,
    ContactIdentityCandidate,
    ImportEntityDecisionKind,
)
from app.services.import_resolution.normalization import ProjectedImportRow


@dataclass(frozen=True)
class EntityMatch:
    decision: ImportEntityDecisionKind
    candidate_entity_id: UUID | None
    confidence: float
    reason_codes: tuple[str, ...]


class DeterministicEntityMatcher:
    def match_company(
        self,
        projected: ProjectedImportRow,
        *,
        source: str,
        external_identities: dict[tuple[str, str], UUID],
        companies: dict[UUID, CompanyResolutionCandidate],
    ) -> EntityMatch:
        warnings = list(projected.projection_warnings)
        if projected.external_company_id:
            identity_key = (source, projected.external_company_id)
            matched_id = external_identities.get(identity_key)
            if matched_id is not None:
                return EntityMatch(
                    ImportEntityDecisionKind.AUTO_MERGE,
                    matched_id,
                    1.0,
                    tuple(["external_identity_match", *warnings]),
                )

        if projected.normalized_domain:
            domain_matches = [
                candidate
                for candidate in companies.values()
                if candidate.normalized_domain == projected.normalized_domain
            ]
            if domain_matches:
                best = max(domain_matches, key=lambda item: self._name_similarity(projected, item))
                conflicts = self._company_conflicts(projected, best)
                if len(domain_matches) > 1:
                    conflicts.append("multiple_domain_candidates")
                if conflicts:
                    return EntityMatch(
                        ImportEntityDecisionKind.REVIEW_REQUIRED,
                        best.company_id,
                        0.76,
                        tuple(["domain_match_with_conflict", *conflicts, *warnings]),
                    )
                return EntityMatch(
                    ImportEntityDecisionKind.AUTO_MERGE,
                    best.company_id,
                    0.96,
                    tuple(["normalized_domain_match", *warnings]),
                )

        if projected.normalized_company_name and projected.normalized_address:
            for candidate in companies.values():
                if (
                    candidate.normalized_name == projected.normalized_company_name
                    and candidate.normalized_address == projected.normalized_address
                ):
                    return EntityMatch(
                        ImportEntityDecisionKind.AUTO_MERGE,
                        candidate.company_id,
                        0.94,
                        tuple(["normalized_name_address_match", *warnings]),
                    )

        review_candidates: list[tuple[float, CompanyResolutionCandidate, list[str]]] = []
        for candidate in companies.values():
            similarity = self._name_similarity(projected, candidate)
            reasons: list[str] = []
            if similarity >= 0.82:
                reasons.append("company_name_similar")
            if (
                projected.normalized_company_phone
                and projected.normalized_company_phone == candidate.normalized_phone
            ):
                reasons.append("phone_auxiliary_match")
            if (
                projected.contact_email_domain
                and projected.contact_email_domain == candidate.normalized_domain
            ):
                reasons.append("email_domain_auxiliary_match")
            if reasons:
                review_candidates.append((similarity, candidate, reasons))
        if review_candidates:
            similarity, candidate, reasons = max(review_candidates, key=lambda item: item[0])
            return EntityMatch(
                ImportEntityDecisionKind.REVIEW_REQUIRED,
                candidate.company_id,
                min(0.79, max(0.5, similarity)),
                tuple([*reasons, *self._company_conflicts(projected, candidate), *warnings]),
            )

        if not projected.company_name or not projected.normalized_company_name:
            return EntityMatch(
                ImportEntityDecisionKind.REJECTED,
                None,
                0.0,
                tuple(["company_name_missing", *warnings]),
            )
        return EntityMatch(
            ImportEntityDecisionKind.AUTO_CREATE,
            None,
            0.65,
            tuple(["no_company_identity_match", *warnings]),
        )

    def match_contact(
        self,
        projected: ProjectedImportRow,
        *,
        company_id: UUID | None,
        contacts: dict[UUID, ContactIdentityCandidate],
        email_index: dict[str, UUID],
        linkedin_index: dict[str, UUID],
    ) -> EntityMatch:
        warnings = list(projected.projection_warnings)
        if projected.contact_email:
            matched_id = email_index.get(projected.contact_email)
            if matched_id is not None:
                return EntityMatch(
                    ImportEntityDecisionKind.AUTO_MERGE,
                    matched_id,
                    1.0,
                    tuple(["global_email_match", *warnings]),
                )
        if projected.normalized_linkedin:
            matched_id = linkedin_index.get(projected.normalized_linkedin)
            if matched_id is not None:
                return EntityMatch(
                    ImportEntityDecisionKind.AUTO_MERGE,
                    matched_id,
                    0.98,
                    tuple(["global_linkedin_match", *warnings]),
                )
        if projected.normalized_contact_name and company_id is not None:
            for candidate in contacts.values():
                if company_id not in candidate.company_ids:
                    continue
                if candidate.normalized_name != projected.normalized_contact_name:
                    continue
                if (
                    projected.normalized_contact_title
                    and candidate.normalized_title == projected.normalized_contact_title
                ):
                    return EntityMatch(
                        ImportEntityDecisionKind.REVIEW_REQUIRED,
                        candidate.contact_id,
                        0.72,
                        tuple(["same_company_name_title", *warnings]),
                    )
                return EntityMatch(
                    ImportEntityDecisionKind.REVIEW_REQUIRED,
                    candidate.contact_id,
                    0.55,
                    tuple(["same_company_name_only", *warnings]),
                )
        if not projected.contact_name:
            return EntityMatch(
                ImportEntityDecisionKind.REJECTED,
                None,
                0.0,
                tuple(["contact_name_missing", *warnings]),
            )
        reasons = ["no_contact_identity_match", *warnings]
        if company_id is None:
            reasons.append("unassigned_contact")
        if projected.is_department_contact:
            reasons.append("department_contact")
        return EntityMatch(
            ImportEntityDecisionKind.AUTO_CREATE,
            None,
            0.65,
            tuple(reasons),
        )

    @staticmethod
    def _name_similarity(
        projected: ProjectedImportRow, candidate: CompanyResolutionCandidate
    ) -> float:
        if not projected.normalized_company_name:
            return 0.0
        return SequenceMatcher(
            None,
            projected.normalized_company_name,
            candidate.normalized_name,
        ).ratio()

    @staticmethod
    def _company_conflicts(
        projected: ProjectedImportRow, candidate: CompanyResolutionCandidate
    ) -> list[str]:
        conflicts: list[str] = []
        if projected.normalized_company_name:
            similarity = SequenceMatcher(
                None,
                projected.normalized_company_name,
                candidate.normalized_name,
            ).ratio()
            if similarity < 0.55:
                conflicts.append("company_name_conflict")
        if (
            projected.normalized_address
            and candidate.normalized_address
            and projected.normalized_address != candidate.normalized_address
        ):
            conflicts.append("company_address_conflict")
        if (
            projected.company_type
            and candidate.company_type
            and projected.company_type != candidate.company_type
        ):
            conflicts.append("company_type_conflict")
        return conflicts
