"""Provider candidate normalization and in-task deduplication."""

from app.domain.discovery import CompanyCandidate
from app.services.discovery.candidates import normalize_domain, prepare_candidates


def candidate(
    name: str,
    *,
    source_url: str,
    website: str | None = None,
    address: str | None = None,
) -> CompanyCandidate:
    return CompanyCandidate(
        source="manual_csv",
        company_name=name,
        source_url=source_url,
        website=website,
        address=address,
    )


def test_normalizes_scheme_and_www_from_domain() -> None:
    assert normalize_domain("HTTPS://WWW.Example.COM/products") == "example.com"


def test_domain_match_wins_even_when_company_names_differ() -> None:
    prepared = prepare_candidates(
        (
            candidate(
                "Northstar Hardware LLC",
                source_url="https://source.example/1",
                website="https://www.northstar.example",
            ),
            candidate(
                "NSH Imports",
                source_url="https://source.example/2",
                website="northstar.example/about",
            ),
        )
    )
    assert prepared[0].duplicate_of_index is None
    assert prepared[1].duplicate_of_index == 0


def test_name_and_address_are_fallback_without_domain() -> None:
    prepared = prepare_candidates(
        (
            candidate(
                "Atlas Hardware, Inc.",
                source_url="record-1",
                address="100 Main St, Dallas TX",
            ),
            candidate(
                "ATLAS HARDWARE LLC",
                source_url="record-2",
                address=" 100  main st,  dallas tx ",
            ),
            candidate(
                "Atlas Hardware",
                source_url="record-3",
                address="200 Main St, Dallas TX",
            ),
        )
    )
    assert prepared[1].duplicate_of_index == 0
    assert prepared[2].duplicate_of_index is None
