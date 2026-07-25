"""WebsiteContactExtractor: deterministic extraction, no fabrication."""

from app.services.contact_discovery import (
    DiscoverySourceType,
    extract_contacts,
    rank_contacts,
)

URL = "https://example.com/contact"


def page(html: str, text: str | None = None) -> list[tuple[str, str, str]]:
    import re

    plain = text if text is not None else re.sub(r"<[^>]+>", " ", html)
    return [(URL, html, plain)]


class TestExtraction:
    def test_mailto_link_is_extracted_with_source(self) -> None:
        contacts = extract_contacts(
            page('<a href="mailto:jane.doe@example.com">Email Jane</a>')
        )
        assert [c.email for c in contacts] == ["jane.doe@example.com"]
        assert contacts[0].source_url == URL

    def test_name_and_title_near_email_become_a_named_contact(self) -> None:
        text = (
            "Our team. Jane Doe, Director of Purchasing. "
            "Reach her at jane.doe@example.com for supplier questions."
        )
        contacts = extract_contacts([(URL, f"<p>{text}</p>", text)])
        named = [c for c in contacts if c.source_type is DiscoverySourceType.NAMED]
        assert named, "expected a named contact"
        assert named[0].name == "Jane Doe"
        assert "Purchasing" in named[0].title
        assert named[0].email == "jane.doe@example.com"
        assert named[0].evidence_snippet in text or named[0].email in named[0].evidence_snippet

    def test_department_mailbox_is_classified_not_named(self) -> None:
        contacts = extract_contacts(page("<p>Write to sales@example.com anytime.</p>"))
        assert contacts[0].source_type is DiscoverySourceType.DEPARTMENT
        assert contacts[0].name == ""

    def test_duplicate_emails_are_deduplicated(self) -> None:
        html = (
            '<a href="mailto:info@example.com">info@example.com</a>'
            "<p>Contact info@example.com</p>"
        )
        contacts = extract_contacts(page(html))
        assert len([c for c in contacts if c.email == "info@example.com"]) == 1

    def test_no_contacts_yields_empty_and_company_only_selection(self) -> None:
        contacts = extract_contacts(page("<p>We make excellent widgets.</p>"))
        assert contacts == []
        selection = rank_contacts(contacts)
        assert selection.primary is None
        assert selection.review_required is True

    def test_nothing_is_fabricated_every_field_comes_from_the_page(self) -> None:
        text = "General inquiries: purchasing@example.com. Call tel anytime."
        html = f'<p>{text}</p><a href="tel:+1 (555) 010-9999">call</a>'
        contacts = extract_contacts([(URL, html, text)])
        for contact in contacts:
            assert contact.name == ""  # no name on the page → no name invented
            if contact.email:
                assert contact.email in text.lower()
            if contact.phone:
                assert contact.phone in html

    def test_noreply_addresses_are_dropped(self) -> None:
        contacts = extract_contacts(page("<p>noreply@example.com</p>"))
        assert contacts == []


class TestRanking:
    def test_named_purchasing_contact_outranks_department_mailbox(self) -> None:
        text = (
            "John Smith, VP of Supply Chain. john.smith@example.com. "
            "Or write sales@example.com."
        )
        selection = rank_contacts(extract_contacts([(URL, f"<p>{text}</p>", text)]))
        assert selection.primary is not None
        assert selection.primary.contact.name == "John Smith"
        assert selection.review_required is False
        assert any("roles=" in reason for reason in selection.primary.reasons)

    def test_department_only_page_requires_review(self) -> None:
        selection = rank_contacts(
            extract_contacts(page("<p>procurement@example.com sales@example.com</p>"))
        )
        assert selection.primary is not None
        assert selection.primary.contact.source_type is DiscoverySourceType.DEPARTMENT
        assert selection.review_required is True
        # purchasing/procurement outranks sales for logistics outreach
        assert selection.primary.contact.email.startswith("procurement")


class TestDepartmentDisplay:
    def test_prefixes_map_to_team_salutations(self) -> None:
        from app.services.contact_discovery import department_display_name

        assert department_display_name("purchasing@example.com") == "Purchasing Team"
        assert department_display_name("procurement@example.com") == "Procurement Team"
        assert department_display_name("imports@example.com") == "Import Team"
        assert department_display_name("logistics@example.com") == "Logistics Team"
        assert department_display_name("operations@example.com") == "Operations Team"
        assert department_display_name("sales@example.com") == "Sales Team"
        assert department_display_name("info@example.com") == "Team"
        assert department_display_name("unknownbox@example.com") == "Team"

    def test_response_display_name_never_invents_a_person(self) -> None:
        from app.schemas.contact_discovery import DiscoveredContactResponse

        [dept] = extract_contacts(
            [("https://example.com/contact", "<p>purchasing@example.com</p>",
              "purchasing@example.com")]
        )
        response = DiscoveredContactResponse.from_contact(dept)
        assert response.name == ""  # the page named no one, so neither do we
        assert response.display_name == "Purchasing Team"
