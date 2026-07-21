"""Decision-role taxonomy: what a job title actually means for freight.

One title, several responsibilities. "Sales and Purchasing" is not a
procurement person *or* a sales person — they are both, and collapsing that
into a single department was how a legitimate buying contact lost their buying
half. Roles are therefore a set, not a choice.

Everything a role means lives here, versioned: its phrases, the phrases that
must not trigger it, how relevant it is to choosing a forwarder, and which
seniority levels make sense for it. Rules scattered through workflows were how
this drifted in the first place.
"""

from dataclasses import dataclass, field
from enum import StrEnum

#: Bump when phrases or relevance change in a way that would alter a stored
#: classification, so an assessment records which vocabulary produced it.
TAXONOMY_VERSION = "decision-role-v1"


class DecisionRole(StrEnum):
    PROCUREMENT = "procurement"
    SOURCING = "sourcing"
    SUPPLY_CHAIN = "supply_chain"
    LOGISTICS = "logistics"
    IMPORT = "import"
    OPERATIONS = "operations"
    INVENTORY = "inventory"
    MERCHANDISING = "merchandising"
    VENDOR_MANAGEMENT = "vendor_management"
    OWNERSHIP = "ownership"
    FINANCE = "finance"
    SALES = "sales"
    MARKETING = "marketing"
    COMPLIANCE = "compliance"
    CUSTOMER_SERVICE = "customer_service"
    ENGINEERING = "engineering"
    HUMAN_RESOURCES = "human_resources"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RoleDefinition:
    """One responsibility, and the words that do and do not signal it.

    `decision_relevance` is how much this role matters when choosing who
    decides on freight — 1.0 for the people who sign the contract, 0.0 for
    roles that never do. It is not seniority and not reachability.
    """

    code: DecisionRole
    name_zh: str
    name_en: str
    description: str
    positive_phrases: tuple[str, ...]
    #: Phrases that veto this role even when a positive one matched.
    negative_phrases: tuple[str, ...] = ()
    #: Roles this one implies. "Import Manager" also buys; "Category Manager"
    #: usually owns the vendor relationship for their category.
    implies: tuple[DecisionRole, ...] = ()
    decision_relevance: float = 0.0
    #: Seniority levels that are meaningful for this role, for later ranking.
    seniority_applicable: bool = True
    aliases: tuple[str, ...] = field(default_factory=tuple)


#: Phrases are matched against a normalized, space-padded title, so a phrase
#: written with surrounding spaces matches a whole word only. "import" without
#: padding would fire on "important"; that is exactly the trap this guards.
ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        code=DecisionRole.PROCUREMENT,
        name_zh="采购",
        name_en="Procurement",
        description="Buys goods and selects suppliers; signs or influences freight terms.",
        positive_phrases=(
            "purchasing",
            "procurement",
            "purchase",
            "procure",
            " buyer ",
            " buyers ",
            " buying ",
        ),
        decision_relevance=1.0,
    ),
    RoleDefinition(
        code=DecisionRole.SOURCING,
        name_zh="寻源",
        name_en="Sourcing",
        description="Finds and qualifies suppliers, often overseas.",
        positive_phrases=("sourcing", "supplier development", "supply manager"),
        implies=(DecisionRole.PROCUREMENT,),
        decision_relevance=0.9,
    ),
    RoleDefinition(
        code=DecisionRole.SUPPLY_CHAIN,
        name_zh="供应链",
        name_en="Supply chain",
        description="Owns the end-to-end flow of goods, including inbound freight.",
        positive_phrases=(
            "supply chain",
            "supply chain management",
            " scm ",
            "supply manager",
        ),
        #: Owning the flow of goods means owning inbound freight — the person a
        #: forwarder actually talks to. Implication is one level deep, so an
        #: *inventory* manager (who only implies supply chain) does not inherit
        #: logistics, but a supply-chain title does.
        implies=(DecisionRole.LOGISTICS,),
        decision_relevance=1.0,
    ),
    RoleDefinition(
        code=DecisionRole.LOGISTICS,
        name_zh="物流",
        name_en="Logistics",
        description="Moves the goods; the most direct counterpart for a forwarder.",
        positive_phrases=(
            "logistics",
            "freight",
            "shipping",
            "transportation",
            "distribution",
            "warehousing",
            "customs",
        ),
        decision_relevance=1.0,
    ),
    RoleDefinition(
        code=DecisionRole.IMPORT,
        name_zh="进口",
        name_en="Import",
        description="Runs inbound international shipments and customs entry.",
        positive_phrases=(
            " import ",
            " imports ",
            " importing ",
            " importer ",
            " import/",
            "/import ",
        ),
        #: An import manager buys freight services even when the title never
        #: says "purchasing".
        implies=(DecisionRole.PROCUREMENT, DecisionRole.LOGISTICS),
        decision_relevance=1.0,
    ),
    RoleDefinition(
        code=DecisionRole.OPERATIONS,
        name_zh="运营",
        name_en="Operations",
        description="Runs day-to-day execution; may or may not own freight.",
        positive_phrases=(" operations ", " operation ", " ops "),
        decision_relevance=0.5,
    ),
    RoleDefinition(
        code=DecisionRole.INVENTORY,
        name_zh="库存",
        name_en="Inventory",
        description="Plans stock levels and replenishment, which drives shipment cadence.",
        positive_phrases=("inventory", "replenishment", "demand planning", "planner"),
        implies=(DecisionRole.SUPPLY_CHAIN,),
        decision_relevance=0.7,
    ),
    RoleDefinition(
        code=DecisionRole.MERCHANDISING,
        name_zh="商品管理",
        name_en="Merchandising",
        description="Owns a product category, usually including its vendors.",
        positive_phrases=("merchandis", "category manager", "category management"),
        implies=(DecisionRole.PROCUREMENT,),
        decision_relevance=0.7,
    ),
    RoleDefinition(
        code=DecisionRole.VENDOR_MANAGEMENT,
        name_zh="供应商管理",
        name_en="Vendor management",
        description="Owns supplier relationships and contracts.",
        positive_phrases=("vendor", "supplier relations", "supplier management"),
        implies=(DecisionRole.PROCUREMENT,),
        decision_relevance=0.8,
    ),
    RoleDefinition(
        code=DecisionRole.OWNERSHIP,
        name_zh="企业主 / 高管",
        name_en="Ownership",
        description="Owns or leads the company; decides everything at a small one.",
        positive_phrases=(
            " owner ",
            " founder ",
            " president ",
            " ceo ",
            " coo ",
            "chief executive",
            "managing director",
            "general manager",
            "proprietor",
        ),
        #: A vice president reports to ownership, they are not it. Without this
        #: veto " president " fires inside "vice president" and a VP of
        #: Purchasing reads as the company owner.
        negative_phrases=("vice president",),
        decision_relevance=0.8,
    ),
    RoleDefinition(
        code=DecisionRole.FINANCE,
        name_zh="财务",
        name_en="Finance",
        description="Controls spend; approves rather than selects.",
        positive_phrases=("finance", "financial", "accounting", "controller", " cfo "),
        decision_relevance=0.3,
    ),
    RoleDefinition(
        code=DecisionRole.SALES,
        name_zh="销售",
        name_en="Sales",
        description="Sells outbound. Rarely chooses an inbound freight forwarder.",
        positive_phrases=(" sales ", " selling ", "account executive", "business development"),
        decision_relevance=0.1,
    ),
    RoleDefinition(
        code=DecisionRole.MARKETING,
        name_zh="市场",
        name_en="Marketing",
        description="Demand generation and brand.",
        positive_phrases=("marketing", "brand", "communications"),
        decision_relevance=0.0,
    ),
    RoleDefinition(
        code=DecisionRole.COMPLIANCE,
        name_zh="合规",
        name_en="Compliance",
        description="Trade compliance, customs classification, regulatory filings.",
        positive_phrases=("compliance", "regulatory", "trade compliance"),
        decision_relevance=0.6,
    ),
    RoleDefinition(
        code=DecisionRole.CUSTOMER_SERVICE,
        name_zh="客户服务",
        name_en="Customer service",
        description="Serves customers after the sale.",
        positive_phrases=("customer service", "customer success", "customer support"),
        decision_relevance=0.1,
    ),
    RoleDefinition(
        code=DecisionRole.ENGINEERING,
        name_zh="工程 / 技术",
        name_en="Engineering",
        description="Builds the product or the systems.",
        positive_phrases=("engineer", "engineering", "developer", " cto ", " it "),
        decision_relevance=0.0,
    ),
    RoleDefinition(
        code=DecisionRole.HUMAN_RESOURCES,
        name_zh="人力资源",
        name_en="Human resources",
        description="People and hiring.",
        positive_phrases=("human resources", " hr ", "recruit", "talent", "people ops"),
        decision_relevance=0.0,
    ),
    RoleDefinition(
        code=DecisionRole.UNKNOWN,
        name_zh="未知",
        name_en="Unknown",
        description="No responsibility could be read from the title.",
        positive_phrases=(),
        decision_relevance=0.0,
        seniority_applicable=False,
    ),
)

ROLES_BY_CODE: dict[DecisionRole, RoleDefinition] = {
    definition.code: definition for definition in ROLE_DEFINITIONS
}


def role_definition(role: DecisionRole) -> RoleDefinition:
    return ROLES_BY_CODE[role]


def decision_relevance(roles: tuple[DecisionRole, ...]) -> float:
    """The strongest freight-decision signal among a person's roles.

    Max rather than sum: someone who both sells and buys is as relevant as a
    buyer, not twice as relevant. Adding roles must never inflate a contact.
    """
    if not roles:
        return 0.0
    return max(role_definition(role).decision_relevance for role in roles)


#: Ordered legacy mapping. `department` is a single value the existing scorer,
#: mappers and API still read; this picks which role stands in for the set.
#: It is a compatibility projection, NOT the classification result — the full
#: answer is `roles`, and anything new should read that.
_LEGACY_DEPARTMENT_ORDER: tuple[tuple[DecisionRole, str], ...] = (
    (DecisionRole.SUPPLY_CHAIN, "supply_chain"),
    (DecisionRole.LOGISTICS, "logistics"),
    (DecisionRole.IMPORT, "logistics"),
    (DecisionRole.PROCUREMENT, "procurement"),
    (DecisionRole.SOURCING, "procurement"),
    (DecisionRole.VENDOR_MANAGEMENT, "procurement"),
    (DecisionRole.MERCHANDISING, "procurement"),
    (DecisionRole.INVENTORY, "supply_chain"),
    (DecisionRole.OPERATIONS, "operations"),
    (DecisionRole.COMPLIANCE, "operations"),
    (DecisionRole.FINANCE, "finance"),
    (DecisionRole.OWNERSHIP, "executive"),
    (DecisionRole.SALES, "sales_marketing"),
    (DecisionRole.MARKETING, "sales_marketing"),
    (DecisionRole.CUSTOMER_SERVICE, "other"),
    (DecisionRole.ENGINEERING, "other"),
    (DecisionRole.HUMAN_RESOURCES, "hr"),
)


def legacy_department(roles: tuple[DecisionRole, ...]) -> str:
    """Compatibility projection of a role set onto the old single department.

    Freight-relevant roles win, so a "Sales and Purchasing" contact reads as
    procurement to the legacy scorer rather than losing their buying half —
    the exact regression this taxonomy exists to end.
    """
    for role, department in _LEGACY_DEPARTMENT_ORDER:
        if role in roles:
            return department
    return "unknown"


def roles_from_legacy_department(department: str) -> tuple[DecisionRole, ...]:
    """Read an old row that predates roles.

    Deliberately one role: a stored department cannot tell us what the second
    responsibility was, and inventing one would be worse than admitting the
    row is coarse. Rows are not back-filled; they simply read as they were.
    """
    mapping = {
        "procurement": DecisionRole.PROCUREMENT,
        "supply_chain": DecisionRole.SUPPLY_CHAIN,
        "logistics": DecisionRole.LOGISTICS,
        "operations": DecisionRole.OPERATIONS,
        "finance": DecisionRole.FINANCE,
        "sales_marketing": DecisionRole.SALES,
        "executive": DecisionRole.OWNERSHIP,
        "hr": DecisionRole.HUMAN_RESOURCES,
    }
    role = mapping.get(department)
    return (role,) if role else (DecisionRole.UNKNOWN,)
