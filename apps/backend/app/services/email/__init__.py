"""Email service: outreach email composition and delivery-related logic."""

from app.services.email.generators import (
    EmailGenerationError,
    FakeEmailDraftGenerator,
    OpenAIEmailDraftGenerator,
)

__all__ = [
    "EmailGenerationError",
    "FakeEmailDraftGenerator",
    "OpenAIEmailDraftGenerator",
]
