"""Research services: extraction and claim validation (v0.2 phase 2)."""

from app.services.research.chunking import (
    CHUNKER_ALGORITHM_VERSION,
    TOKENIZER_PROFILE,
    ChunkingAction,
    ChunkingConfig,
    ChunkingConflictError,
    ChunkingMetrics,
    ChunkingPlan,
    ChunkingResult,
    DeterministicDocumentChunker,
    DeterministicLocalTokenizer,
    ResearchDocumentChunkingService,
    render_chunk_visualization,
)
from app.services.research.documents import (
    DocumentIngestionAction,
    ResearchDocumentIngestionInput,
    ResearchDocumentIngestionResult,
    ResearchDocumentIngestionService,
    canonicalize_document_url,
)
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
    "CHUNKER_ALGORITHM_VERSION",
    "TOKENIZER_PROFILE",
    "ChunkingAction",
    "ChunkingConfig",
    "ChunkingConflictError",
    "ChunkingMetrics",
    "ChunkingPlan",
    "ChunkingResult",
    "DeterministicDocumentChunker",
    "DeterministicLocalTokenizer",
    "DocumentIngestionAction",
    "ExtractionError",
    "ExtractionErrorCode",
    "ExtractionInput",
    "ExtractionUsage",
    "FakeResearchExtractor",
    "OpenAIResearchExtractor",
    "PageContent",
    "ResearchExtractor",
    "ResearchDocumentIngestionInput",
    "ResearchDocumentIngestionResult",
    "ResearchDocumentIngestionService",
    "ResearchDocumentChunkingService",
    "render_chunk_visualization",
    "ValidationOutcome",
    "canonicalize_document_url",
]
