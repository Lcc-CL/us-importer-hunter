"""Contact deduplication (mvp rules, ADR-0022):

1. same company + same valid email          → strong MATCHED
2. same company + same LinkedIn URL         → strong MATCHED
3. same company + same name AND same title  → medium MATCHED
4. same name but conflicting channels       → POSSIBLE_MATCH (human call)
5. name alone is never a global identity.
"""

from uuid import UUID

from app.domain.contact import ContactMatch, ContactMatchKind, JobTitle, PersonName
from app.domain.repositories import ContactRepository


class RepositoryContactDeduplicator:
    def __init__(self, contacts: ContactRepository) -> None:
        self._contacts = contacts

    async def classify(
        self,
        company_id: UUID,
        name: PersonName,
        title: JobTitle | None,
        email_normalized: str | None,
        linkedin_normalized: str | None,
    ) -> ContactMatch:
        if email_normalized:
            by_email = await self._contacts.find_by_email(company_id, email_normalized)
            if by_email is not None:
                return ContactMatch(
                    kind=ContactMatchKind.MATCHED,
                    matched_contact_id=by_email.id,
                    reason=f"same company + same email {email_normalized!r}",
                )
        if linkedin_normalized:
            by_linkedin = await self._contacts.find_by_linkedin_url(
                company_id, linkedin_normalized
            )
            if by_linkedin is not None:
                return ContactMatch(
                    kind=ContactMatchKind.MATCHED,
                    matched_contact_id=by_linkedin.id,
                    reason="same company + same linkedin profile",
                )

        for existing in await self._contacts.list_for_company(company_id):
            if existing.name.normalized != name.normalized:
                continue
            if (
                title is not None
                and existing.title is not None
                and existing.title.normalized == title.normalized
            ):
                return ContactMatch(
                    kind=ContactMatchKind.MATCHED,
                    matched_contact_id=existing.id,
                    reason="same company + same normalized name and title",
                )
            return ContactMatch(
                kind=ContactMatchKind.POSSIBLE_MATCH,
                matched_contact_id=existing.id,
                reason=(
                    "same name but titles/channels do not corroborate — "
                    "not merging automatically"
                ),
            )

        return ContactMatch(
            kind=ContactMatchKind.NEW, matched_contact_id=None, reason="no match at this company"
        )
