"""Exception hierarchy.

Deeper layers raise these typed exceptions; API routes translate them
into HTTP responses. Only routes raise HTTPException.
"""


class ApplicationError(Exception):
    """Base for typed application failures safe to map at the API edge."""


class ResourceNotFoundError(ApplicationError):
    """A requested aggregate or nested resource does not exist."""


class ApplicationConflictError(ApplicationError):
    """The requested operation conflicts with current domain state."""


class ProviderUnavailableError(ApplicationError):
    """An explicitly selected external provider cannot serve the request."""


__all__ = [
    "ApplicationConflictError",
    "ApplicationError",
    "ProviderUnavailableError",
    "ResourceNotFoundError",
]
