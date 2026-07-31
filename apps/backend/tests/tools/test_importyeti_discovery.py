"""ImportYeti discovery fails closed until an official API contract exists."""

import pytest

from app.domain.discovery import CompanyDiscoveryQuery, DiscoveryProviderUnavailable
from app.tools.importyeti import ImportYetiCompanyDiscoveryProvider


async def test_importyeti_reports_api_capability_blocker_without_scraping() -> None:
    provider = ImportYetiCompanyDiscoveryProvider()
    query = CompanyDiscoveryQuery(
        original_prompt="帮我找 20 家北美五金进口商",
        requested_count=20,
        effective_count=20,
        region="North America",
        category="hardware",
        keywords=("五金", "hardware", "importer"),
    )
    with pytest.raises(DiscoveryProviderUnavailable) as caught:
        await provider.search(query)
    assert caught.value.error_code == "REAL_PROVIDER_BLOCKED_BY_API_CAPABILITY"
    assert "website scraping is disabled" in str(caught.value)
