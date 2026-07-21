"""Titles carry responsibilities, plural — and some words lie about them.

The traps in this file are not hypothetical. "Important Accounts Manager"
matching import, and "Coordinator" matching "coo", were both real defects
found by running the vocabulary over live data. The rest are the ones that
would have been found next.
"""

import pytest

from app.domain.contact import SeniorityLevel
from app.domain.contact.roles import (
    ROLE_DEFINITIONS,
    ROLES_BY_CODE,
    TAXONOMY_VERSION,
    DecisionRole,
    decision_relevance,
    legacy_department,
    roles_from_legacy_department,
)
from app.services.contact.role_matcher import DeterministicRoleMatcher, classify_title
from app.services.contact.title_normalizer import normalize_title


def roles_of(title: str) -> set[DecisionRole]:
    return set(classify_title(title).roles)


# -- taxonomy -------------------------------------------------------------


class TestTaxonomy:
    def test_every_role_in_the_enum_has_a_definition(self) -> None:
        assert {definition.code for definition in ROLE_DEFINITIONS} == set(DecisionRole)

    def test_every_definition_is_bilingual_and_described(self) -> None:
        for definition in ROLE_DEFINITIONS:
            assert definition.name_zh.strip()
            assert definition.name_en.strip()
            assert definition.description.strip()

    def test_relevance_is_a_ratio(self) -> None:
        for definition in ROLE_DEFINITIONS:
            assert 0.0 <= definition.decision_relevance <= 1.0

    def test_freight_roles_outrank_sales_for_relevance(self) -> None:
        assert (
            ROLES_BY_CODE[DecisionRole.PROCUREMENT].decision_relevance
            > ROLES_BY_CODE[DecisionRole.SALES].decision_relevance
        )
        assert (
            ROLES_BY_CODE[DecisionRole.LOGISTICS].decision_relevance
            > ROLES_BY_CODE[DecisionRole.MARKETING].decision_relevance
        )

    def test_version_is_recorded(self) -> None:
        assert TAXONOMY_VERSION == "decision-role-v1"

    def test_adding_a_role_never_inflates_relevance(self) -> None:
        """Someone who sells *and* buys is as relevant as a buyer, not more."""
        buyer_only = decision_relevance((DecisionRole.PROCUREMENT,))
        both = decision_relevance((DecisionRole.SALES, DecisionRole.PROCUREMENT))
        assert both == buyer_only


# -- normalizer -----------------------------------------------------------


class TestTitleNormalizer:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("VP of Purchasing", "vice president of purchasing"),
            ("Sr. Buyer", "senior buyer"),
            ("Purch. Mgr", "purchasing manager"),
            ("Dir, Ops", "director operations"),
            ("SCM Lead", "supply chain management lead"),
            ("Sales & Purchasing", "sales and purchasing"),
        ],
    )
    def test_abbreviations_expand(self, raw: str, expected: str) -> None:
        assert normalize_title(raw).normalized_title == expected

    def test_accents_and_spacing_are_normalized(self) -> None:
        assert normalize_title("  Directeur   Achats ").normalized_title == "directeur achats"

    def test_separators_split_into_phrases(self) -> None:
        title = normalize_title("Owner / Buyer")
        assert title.phrases == ("owner", "buyer")

    def test_region_noise_is_dropped_from_tokens(self) -> None:
        title = normalize_title("Purchasing Manager, EMEA")
        assert "emea" not in title.tokens
        assert "purchasing" in title.tokens

    def test_former_is_flagged(self) -> None:
        assert normalize_title("Former Purchasing Manager").historical_role is True
        assert normalize_title("Purchasing Manager").historical_role is False

    def test_assistant_is_flagged(self) -> None:
        assert normalize_title("Assistant Buyer").assistant_role is True
        assert normalize_title("Buyer").assistant_role is False

    def test_interim_is_flagged(self) -> None:
        assert normalize_title("Interim Logistics Director").interim_role is True

    def test_empty_title_is_safe(self) -> None:
        title = normalize_title(None)
        assert title.normalized_title == ""
        assert title.seniority is SeniorityLevel.UNKNOWN


# -- multi-role classification -------------------------------------------


class TestMultiRoleClassification:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Sales and Purchasing", {DecisionRole.SALES, DecisionRole.PROCUREMENT}),
            (
                "Director of Sales and Procurement",
                {DecisionRole.SALES, DecisionRole.PROCUREMENT},
            ),
            ("Owner / Buyer", {DecisionRole.OWNERSHIP, DecisionRole.PROCUREMENT}),
            (
                "Category Manager — Hardware",
                {DecisionRole.MERCHANDISING, DecisionRole.PROCUREMENT},
            ),
            (
                "Vendor Relations Manager",
                {DecisionRole.VENDOR_MANAGEMENT, DecisionRole.PROCUREMENT},
            ),
            (
                "Global Supply Manager",
                {DecisionRole.SOURCING, DecisionRole.SUPPLY_CHAIN},
            ),
            ("Import Compliance Manager", {DecisionRole.IMPORT, DecisionRole.COMPLIANCE}),
            (
                "Inventory and Replenishment Manager",
                {DecisionRole.INVENTORY, DecisionRole.SUPPLY_CHAIN},
            ),
            ("Vice President, Purchasing", {DecisionRole.PROCUREMENT}),
        ],
    )
    def test_expected_roles_are_present(
        self, title: str, expected: set[DecisionRole]
    ) -> None:
        assert expected.issubset(roles_of(title)), roles_of(title)

    def test_supply_chain_and_operations_covers_three(self) -> None:
        roles = roles_of("Supply Chain and Operations Director")
        assert {
            DecisionRole.SUPPLY_CHAIN,
            DecisionRole.OPERATIONS,
            DecisionRole.LOGISTICS,
        }.issubset(roles)

    def test_classification_is_deterministic(self) -> None:
        first = classify_title("Sales and Purchasing")
        second = classify_title("Sales and Purchasing")
        assert first.roles == second.roles
        assert first.confidence == second.confidence

    def test_method_and_version_are_reported(self) -> None:
        result = classify_title("Purchasing Manager")
        assert result.method == "deterministic"
        assert result.taxonomy_version == TAXONOMY_VERSION
        assert result.reasons


# -- the traps ------------------------------------------------------------


class TestMisclassificationTraps:
    def test_important_accounts_manager_is_not_an_importer(self) -> None:
        roles = roles_of("Important Accounts Manager")
        assert DecisionRole.IMPORT not in roles

    def test_import_manager_is_import_and_buys(self) -> None:
        roles = roles_of("Import Manager")
        assert DecisionRole.IMPORT in roles
        assert DecisionRole.PROCUREMENT in roles

    def test_coordinator_is_not_c_level(self) -> None:
        assert normalize_title("Coordinator").seniority is not SeniorityLevel.C_LEVEL
        assert normalize_title("Logistics Coordinator").seniority is SeniorityLevel.SPECIALIST

    def test_purchasing_coordinator_buys_without_being_an_executive(self) -> None:
        assert DecisionRole.PROCUREMENT in roles_of("Purchasing Coordinator")
        assert normalize_title("Purchasing Coordinator").seniority is (
            SeniorityLevel.SPECIALIST
        )

    def test_former_purchasing_manager_is_flagged_not_current(self) -> None:
        result = classify_title("Former Purchasing Manager")
        assert DecisionRole.PROCUREMENT in result.roles
        assert result.historical_role is True
        assert any("former" in warning for warning in result.warnings)

    def test_assistant_buyer_ranks_below_buyer(self) -> None:
        assistant = classify_title("Assistant Buyer")
        buyer = classify_title("Buyer")

        assert DecisionRole.PROCUREMENT in assistant.roles
        assert assistant.assistant_role is True
        assert buyer.assistant_role is False
        # The difference has to be visible to a ranker, not just cosmetic.
        assert normalize_title("Assistant Buyer").seniority is SeniorityLevel.SPECIALIST
        assert normalize_title("Buyer").seniority is not SeniorityLevel.SPECIALIST

    def test_independent_sales_agent_does_not_buy(self) -> None:
        roles = roles_of("Independent Sales Agent")
        assert DecisionRole.SALES in roles
        assert DecisionRole.PROCUREMENT not in roles

    def test_sales_and_purchasing_keeps_both(self) -> None:
        roles = roles_of("Sales and Purchasing")
        assert DecisionRole.SALES in roles
        assert DecisionRole.PROCUREMENT in roles

    def test_sales_and_operations_does_not_gain_procurement(self) -> None:
        roles = roles_of("Vice President, Sales and Operations")
        assert {DecisionRole.SALES, DecisionRole.OPERATIONS}.issubset(roles)
        assert DecisionRole.PROCUREMENT not in roles

    def test_customer_success_operations_is_not_a_freight_decision_maker(self) -> None:
        roles = roles_of("Customer Success Operations Manager")
        assert DecisionRole.CUSTOMER_SERVICE in roles
        assert DecisionRole.OPERATIONS in roles
        assert DecisionRole.PROCUREMENT not in roles
        assert DecisionRole.LOGISTICS not in roles
        # Operations alone is a weak signal, not a decision maker.
        assert decision_relevance(tuple(roles)) < 1.0


# -- the three trial companies -------------------------------------------


class TestTrialCompanyRegression:
    def test_house_hasson_sales_and_purchasing(self) -> None:
        roles = roles_of("Sales and Purchasing")
        assert {DecisionRole.SALES, DecisionRole.PROCUREMENT}.issubset(roles)

    def test_marathon_vice_president_purchasing(self) -> None:
        result = classify_title("vice president, purchasing")
        assert DecisionRole.PROCUREMENT in result.roles
        # A VP of Purchasing is senior, but not the company owner: " president "
        # must not fire inside "vice president".
        assert DecisionRole.OWNERSHIP not in result.roles
        assert normalize_title("vice president, purchasing").seniority in (
            SeniorityLevel.C_LEVEL,
            SeniorityLevel.VP,
        )

    def test_elite_sales_manager_sells_only(self) -> None:
        roles = roles_of("Sales Manager")
        assert roles == {DecisionRole.SALES}
        for forbidden in (
            DecisionRole.PROCUREMENT,
            DecisionRole.IMPORT,
            DecisionRole.LOGISTICS,
        ):
            assert forbidden not in roles


# -- legacy compatibility -------------------------------------------------


class TestLegacyDepartmentMapping:
    def test_freight_roles_win_the_projection(self) -> None:
        """A combined title must not read as sales to the old scorer."""
        assert legacy_department((DecisionRole.SALES, DecisionRole.PROCUREMENT)) == (
            "procurement"
        )

    @pytest.mark.parametrize(
        ("roles", "expected"),
        [
            ((DecisionRole.SUPPLY_CHAIN,), "supply_chain"),
            ((DecisionRole.IMPORT,), "logistics"),
            ((DecisionRole.SOURCING,), "procurement"),
            ((DecisionRole.OWNERSHIP,), "executive"),
            ((DecisionRole.SALES,), "sales_marketing"),
            ((DecisionRole.UNKNOWN,), "unknown"),
        ],
    )
    def test_projection_targets(
        self, roles: tuple[DecisionRole, ...], expected: str
    ) -> None:
        assert legacy_department(roles) == expected

    def test_old_rows_read_as_a_single_role(self) -> None:
        """A stored department cannot say what the second responsibility was;
        inventing one would be worse than admitting the row is coarse."""
        assert roles_from_legacy_department("procurement") == (DecisionRole.PROCUREMENT,)
        assert roles_from_legacy_department("sales_marketing") == (DecisionRole.SALES,)
        assert roles_from_legacy_department("nonsense") == (DecisionRole.UNKNOWN,)


class TestMatcherProtocol:
    def test_matcher_reports_its_method_honestly(self) -> None:
        """It is phrase matching. Naming it semantic would tell a reviewer they
        can rely on something that is not there."""
        assert DeterministicRoleMatcher().method == "deterministic"
