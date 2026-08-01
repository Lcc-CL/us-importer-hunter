"""Company deduplication: does this claim describe a company we know?

Implements the domain protocol CompanyDeduplicationService. MVP rules,
in priority order:
1. same website host when one is available;
2. exact normalized-name match.
Fuzzy matching is a later, evidence-driven upgrade.
"""

from uuid import UUID

from app.domain.repositories import CompanyRepository
from app.domain.values import CompanyName, WebsiteUrl


class RepositoryCompanyDeduplicator:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    async def find_canonical(self, name: CompanyName, website: WebsiteUrl | None) -> UUID | None:
        if website is not None:
            by_host = await self._companies.find_by_website_host(website.host)
            if by_host is not None:
                return by_host.id
        by_name = await self._companies.find_by_normalized_name(name)
        if by_name is not None:
            return by_name.id
        return None
