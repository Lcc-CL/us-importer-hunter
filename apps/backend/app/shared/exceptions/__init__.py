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


class InvalidInputError(ApplicationError):
    """Input passed transport validation but is invalid for an application use case."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


__all__ = [
    "ApplicationConflictError",
    "ApplicationError",
    "InvalidInputError",
    "ProviderUnavailableError",
    "ResourceNotFoundError",
]
