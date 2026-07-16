"""Domain exceptions: business rule violations, independent of any framework.

Deeper meaning of each exception is the business rule it protects; API
layers translate these into HTTP responses, never the other way around.
"""


class DomainError(Exception):
    """Base class for every business rule violation."""


class InvalidCompanyName(DomainError):
    """Company names must be non-empty, printable and of sane length."""


class InvalidWebsiteUrl(DomainError):
    """Website URLs must be http(s) and contain a resolvable-looking host."""


class InvalidEmailAddress(DomainError):
    """Email addresses must have a plausible local@domain.tld shape."""


class InvalidOpportunityScore(DomainError):
    """Opportunity scores live in the 0–100 range."""


class InvalidConfidence(DomainError):
    """Confidence lives in the 0–1 range."""


class InvalidStateTransition(DomainError):
    """The requested lifecycle transition is not allowed from the current state."""


class MissingEvidence(DomainError):
    """A judgment was attempted without the evidence or reasons that justify it."""


class DuplicateOperation(DomainError):
    """The operation was already performed (idempotency / duplicate protection)."""
