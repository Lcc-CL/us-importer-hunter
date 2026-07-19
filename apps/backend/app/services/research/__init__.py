"""Research services: extraction and claim validation (v0.2 phase 2)."""

from app.services.research.extractors import (
    FAKE_PROMPT_VERSION,
    ExtractionInput,
    FakeResearchExtractor,
    ResearchExtractor,
)
from app.services.research.openai_extractor import (
    MAX_ATTEMPTS,
    ExtractionError,
    ExtractionErrorCode,
    ExtractionUsage,
    OpenAIResearchExtractor,
)
from app.services.research.validator import (
    ClaimValidator,
    PageContent,
    ValidationOutcome,
)

__all__ = [
    "FAKE_PROMPT_VERSION",
    "MAX_ATTEMPTS",
    "ClaimValidator",
    "ExtractionError",
    "ExtractionErrorCode",
    "ExtractionInput",
    "ExtractionUsage",
    "FakeResearchExtractor",
    "OpenAIResearchExtractor",
    "PageContent",
    "ResearchExtractor",
    "ValidationOutcome",
]
