"""Company sources are audit rows; the summary that renders them is not.

Two references to the same site are two rows, correctly — and collapsing them
for display is what stops the UI from keying a list on a value that is not
unique. Neither direction may quietly lose the other's guarantee.
"""

from datetime import UTC, datetime

from app.domain.values import SourceReference
from app.schemas.mvp import _summarize_sources

AT = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def ref(source: str, reference: str) -> SourceReference:
    return SourceReference(source=source, reference=reference, retrieved_at=AT)


class TestSummarizeSources:
    def test_same_source_twice_collapses_to_one_entry_with_a_count(self) -> None:
        """The exact shape that produced the duplicate-key crash: one site,
        two pages, two rows both named company_website."""
        summary = _summarize_sources(
            (
                ref("company_website", "http://elitesalesinc.com/"),
                ref("company_website", "https://elitesalesinc.com/indiana-warehouse"),
            )
        )

        assert len(summary) == 1
        assert summary[0].source == "company_website"
        assert summary[0].reference_count == 2

    def test_distinct_sources_are_kept_separately(self) -> None:
        summary = _summarize_sources(
            (
                ref("company_website", "https://acme.example/"),
                ref("importyeti", "https://importyeti.example/acme"),
            )
        )

        assert [item.source for item in summary] == ["company_website", "importyeti"]
        assert all(item.reference_count == 1 for item in summary)

    def test_names_are_unique_so_the_ui_can_key_on_them(self) -> None:
        summary = _summarize_sources(
            tuple(ref("company_website", f"https://acme.example/{i}") for i in range(5))
        )
        names = [item.source for item in summary]

        assert len(names) == len(set(names))
        assert summary[0].reference_count == 5

    def test_first_seen_order_is_preserved(self) -> None:
        summary = _summarize_sources(
            (
                ref("importyeti", "https://importyeti.example/a"),
                ref("company_website", "https://acme.example/"),
                ref("importyeti", "https://importyeti.example/b"),
            )
        )

        assert [item.source for item in summary] == ["importyeti", "company_website"]
        assert summary[0].reference_count == 2

    def test_whitespace_variants_are_the_same_source(self) -> None:
        summary = _summarize_sources(
            (
                ref("company_website", "https://acme.example/"),
                ref("  company_website  ", "https://acme.example/about"),
            )
        )

        assert len(summary) == 1
        assert summary[0].reference_count == 2

    def test_no_sources_yields_no_entries(self) -> None:
        assert _summarize_sources(()) == []
