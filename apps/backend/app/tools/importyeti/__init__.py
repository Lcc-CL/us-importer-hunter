"""ImportYeti company-discovery adapter boundary.

ImportYeti's public site currently documents its searchable customs dataset but
does not publish an official Data API base URL, authentication contract, or
response schema. D1 therefore fails closed instead of scraping the website or
inventing an API contract.
"""

from app.domain.discovery import (
    CompanyDiscoveryQuery,
    CompanyDiscoverySearchResult,
    DiscoveryProviderUnavailable,
)


class ImportYetiCompanyDiscoveryProvider:
    provider_name = "importyeti"

    async def search(self, query: CompanyDiscoveryQuery) -> CompanyDiscoverySearchResult:
        del query
        raise DiscoveryProviderUnavailable(
            "REAL_PROVIDER_BLOCKED_BY_API_CAPABILITY: ImportYeti official Data API capability "
            "is not publicly documented or configured; website scraping is disabled"
        )


__all__ = ["ImportYetiCompanyDiscoveryProvider"]
