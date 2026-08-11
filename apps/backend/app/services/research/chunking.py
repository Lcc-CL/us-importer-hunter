"""Deterministic structure-aware chunking without embeddings or LLMs."""

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from app.domain.exceptions import DomainError
from app.domain.repositories import ResearchDocumentChunkRepository
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentChunk,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
)

TOKENIZER_PROFILE = "unicode-lexical-v1"
CHUNKER_ALGORITHM_VERSION = "structure-recursive-v1"

_TOKEN_PATTERN = re.compile(
    r"[A-Za-z0-9]+(?:['’._/-][A-Za-z0-9]+)*|"
    r"[\u3400-\u4dbf\u4e00-\u9fff]|"
    r"[^\w\s]",
    re.UNICODE,
)
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_PAGE_MARKER = re.compile(r"^\[+\s*page\s+(\d+)\s*\]+$", re.IGNORECASE)
_SENTENCE_END = frozenset({".", "!", "?", "。", "！", "？"})
_BOILERPLATE_HINTS = (
    "cookie settings",
    "privacy policy",
    "terms of use",
    "terms and conditions",
    "all rights reserved",
    "subscribe to our newsletter",
    "sign up for our newsletter",
    "contact us today",
    "request a quote",
    "accept all cookies",
)


class ChunkingAction(StrEnum):
    CREATED = "created"
    REUSED = "reused"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_INELIGIBLE = "skipped_ineligible"


class ChunkingConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 500
    hard_max_tokens: int = 900
    overlap_tokens: int = 80

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if self.hard_max_tokens < self.target_tokens:
            raise ValueError("hard_max_tokens must be at least target_tokens")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be non-negative and below target_tokens")

    @property
    def version(self) -> str:
        settings = (
            f"target={self.target_tokens};hard={self.hard_max_tokens};"
            f"overlap={self.overlap_tokens};tokenizer={TOKENIZER_PROFILE}"
        )
        fingerprint = sha256(settings.encode("utf-8")).hexdigest()[:12]
        return f"{CHUNKER_ALGORITHM_VERSION}:{fingerprint}"


@dataclass(frozen=True)
class TokenSpan:
    start: int
    end: int
    text: str


class TokenCounter(Protocol):
    profile: str

    def spans(self, text: str, *, offset: int = 0) -> tuple[TokenSpan, ...]: ...

    def count(self, text: str) -> int: ...


class DeterministicLocalTokenizer:
    profile = TOKENIZER_PROFILE

    def spans(self, text: str, *, offset: int = 0) -> tuple[TokenSpan, ...]:
        return tuple(
            TokenSpan(
                start=offset + match.start(),
                end=offset + match.end(),
                text=match.group(0),
            )
            for match in _TOKEN_PATTERN.finditer(text)
        )

    def count(self, text: str) -> int:
        return len(self.spans(text))


@dataclass(frozen=True)
class ChunkingMetrics:
    source_tokens: int
    emitted_tokens: int
    duplicate_tokens: int
    boilerplate_tokens: int
    overlap_tokens: int

    @property
    def duplicate_ratio(self) -> float:
        return _ratio(self.duplicate_tokens, self.source_tokens)

    @property
    def boilerplate_ratio(self) -> float:
        return _ratio(self.boilerplate_tokens, self.source_tokens)

    @property
    def overlap_ratio(self) -> float:
        return _ratio(self.overlap_tokens, self.emitted_tokens)


@dataclass(frozen=True)
class ChunkingPlan:
    chunks: tuple[ResearchDocumentChunk, ...]
    metrics: ChunkingMetrics
    chunker_version: str
    tokenizer_profile: str


@dataclass(frozen=True)
class ChunkingResult:
    action: ChunkingAction
    chunks: tuple[ResearchDocumentChunk, ...]
    metrics: ChunkingMetrics | None


@dataclass(frozen=True)
class _Line:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class _Section:
    start: int
    end: int
    heading_path: tuple[str, ...]
    page_number: int | None
    section_type: str
    merged_heading_paths: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class _Slice:
    start: int
    end: int
    overlap_tokens: int
    split: bool


class DeterministicDocumentChunker:
    def __init__(
        self,
        config: ChunkingConfig | None = None,
        tokenizer: TokenCounter | None = None,
    ) -> None:
        self.config = config or ChunkingConfig()
        self.tokenizer = tokenizer or DeterministicLocalTokenizer()

    def chunk(self, document: ResearchDocument) -> ChunkingPlan:
        if document.status is not ResearchDocumentStatus.READY or not document.is_current:
            raise DomainError("only current ready research documents can be chunked")
        if document.duplicate_of_document_id is not None:
            raise DomainError("duplicate research documents reuse their content root chunks")

        lines = _source_lines(document.content)
        sections, duplicate_tokens, boilerplate_tokens = self._sections(document, lines)
        sections = self._merge_short_sections(document.content, sections)
        chunks: list[ResearchDocumentChunk] = []
        emitted_tokens = 0
        overlap_tokens = 0
        for section in sections:
            slices = self._split_section(document.content, section)
            for section_slice in slices:
                content = document.content[section_slice.start : section_slice.end]
                token_count = self.tokenizer.count(content)
                metadata = {
                    "source_type": document.source_type.value,
                    "section_type": section.section_type,
                    "page_number": section.page_number,
                    "overlap_tokens": section_slice.overlap_tokens,
                    "split_from_oversized_section": section_slice.split,
                    "merged_heading_paths": [list(path) for path in section.merged_heading_paths],
                    "target_tokens": self.config.target_tokens,
                    "hard_max_tokens": self.config.hard_max_tokens,
                    "configured_overlap_tokens": self.config.overlap_tokens,
                }
                chunks.append(
                    ResearchDocumentChunk.create(
                        document=document,
                        chunk_index=len(chunks),
                        content=content,
                        token_count=token_count,
                        start_offset=section_slice.start,
                        end_offset=section_slice.end,
                        heading_path=section.heading_path,
                        metadata=metadata,
                        chunker_version=self.config.version,
                        tokenizer_profile=self.tokenizer.profile,
                    )
                )
                emitted_tokens += token_count
                overlap_tokens += section_slice.overlap_tokens

        if not chunks:
            raise DomainError("research document has no eligible chunk content")
        return ChunkingPlan(
            chunks=tuple(chunks),
            metrics=ChunkingMetrics(
                source_tokens=self.tokenizer.count(document.content),
                emitted_tokens=emitted_tokens,
                duplicate_tokens=duplicate_tokens,
                boilerplate_tokens=boilerplate_tokens,
                overlap_tokens=overlap_tokens,
            ),
            chunker_version=self.config.version,
            tokenizer_profile=self.tokenizer.profile,
        )

    def _sections(
        self, document: ResearchDocument, lines: tuple[_Line, ...]
    ) -> tuple[list[_Section], int, int]:
        sections: list[_Section] = []
        heading_stack: list[str] = []
        current_start: int | None = None
        current_end: int | None = None
        current_heading: tuple[str, ...] = ()
        current_page: int | None = (
            1 if document.source_type is ResearchDocumentSourceType.PDF else None
        )
        seen_lines: set[str] = set()
        duplicate_tokens = 0
        boilerplate_tokens = 0

        def flush() -> None:
            nonlocal current_start, current_end
            if current_start is None or current_end is None:
                return
            sections.append(
                _Section(
                    start=current_start,
                    end=current_end,
                    heading_path=current_heading,
                    page_number=current_page,
                    section_type=_section_type(document.source_type, current_page),
                    merged_heading_paths=(current_heading,),
                )
            )
            current_start = None
            current_end = None

        for position, line in enumerate(lines):
            page_match = _PAGE_MARKER.match(line.text)
            if page_match:
                flush()
                current_page = int(page_match.group(1))
                continue

            normalized = " ".join(line.text.casefold().split())
            token_count = self.tokenizer.count(line.text)
            if _is_boilerplate(normalized):
                flush()
                boilerplate_tokens += token_count
                continue
            if normalized in seen_lines and token_count >= 3:
                flush()
                duplicate_tokens += token_count
                continue
            seen_lines.add(normalized)

            heading = _heading(line.text, document.source_type, position)
            if heading is not None:
                flush()
                level, title = heading
                heading_stack[level - 1 :] = [title]
                current_heading = tuple(heading_stack)
                current_start = line.start
                current_end = line.end
                continue

            if current_start is None:
                current_start = line.start
                current_heading = tuple(heading_stack)
            current_end = line.end

        flush()
        return sections, duplicate_tokens, boilerplate_tokens

    def _merge_short_sections(
        self, content: str, sections: list[_Section]
    ) -> list[_Section]:
        merged: list[_Section] = []
        for section in sections:
            if not merged:
                merged.append(section)
                continue
            previous = merged[-1]
            gap = content[previous.end : section.start]
            combined = content[previous.start : section.end]
            if (
                previous.page_number == section.page_number
                and not gap.strip()
                and self.tokenizer.count(combined) <= self.config.target_tokens
            ):
                merged[-1] = _Section(
                    start=previous.start,
                    end=section.end,
                    heading_path=previous.heading_path or section.heading_path,
                    page_number=previous.page_number,
                    section_type=previous.section_type,
                    merged_heading_paths=(
                        *previous.merged_heading_paths,
                        *section.merged_heading_paths,
                    ),
                )
            else:
                merged.append(section)
        return merged

    def _split_section(self, content: str, section: _Section) -> tuple[_Slice, ...]:
        section_text = content[section.start : section.end]
        tokens = self.tokenizer.spans(section_text, offset=section.start)
        if len(tokens) <= self.config.hard_max_tokens:
            return (_Slice(section.start, section.end, 0, False),)

        sentence_ends = _sentence_end_token_indexes(content, tokens)
        slices: list[_Slice] = []
        start_index = 0
        pending_overlap = 0
        while start_index < len(tokens):
            hard_end = min(start_index + self.config.hard_max_tokens, len(tokens))
            target_end = min(start_index + self.config.target_tokens, hard_end)
            end_index = _choose_end_index(
                sentence_ends,
                start_index=start_index,
                target_end=target_end,
                hard_end=hard_end,
            )
            start_offset = tokens[start_index].start
            end_offset = tokens[end_index - 1].end
            slices.append(_Slice(start_offset, end_offset, pending_overlap, True))
            if end_index >= len(tokens):
                break
            next_start = _choose_overlap_start(
                sentence_ends,
                current_start=start_index,
                end_index=end_index,
                overlap_tokens=self.config.overlap_tokens,
            )
            pending_overlap = end_index - next_start
            start_index = next_start
        return tuple(slices)


class ResearchDocumentChunkingService:
    def __init__(self, chunker: DeterministicDocumentChunker | None = None) -> None:
        self.chunker = chunker or DeterministicDocumentChunker()

    async def execute(
        self,
        repository: ResearchDocumentChunkRepository,
        document: ResearchDocument,
    ) -> ChunkingResult:
        if document.status is not ResearchDocumentStatus.READY or not document.is_current:
            return ChunkingResult(ChunkingAction.SKIPPED_INELIGIBLE, (), None)
        if document.duplicate_of_document_id is not None:
            return ChunkingResult(ChunkingAction.SKIPPED_DUPLICATE, (), None)

        plan = self.chunker.chunk(document)
        await repository.lock_chunking_scope(document.id, plan.chunker_version)
        existing = await repository.list_for_document(document.id, plan.chunker_version)
        if existing:
            if tuple(chunk.id for chunk in existing) != tuple(chunk.id for chunk in plan.chunks):
                raise ChunkingConflictError(
                    "persisted chunks do not match deterministic chunking plan"
                )
            return ChunkingResult(ChunkingAction.REUSED, tuple(existing), plan.metrics)
        await repository.add_many(plan.chunks)
        return ChunkingResult(ChunkingAction.CREATED, plan.chunks, plan.metrics)


def render_chunk_visualization(plan: ChunkingPlan, *, preview_chars: int = 100) -> str:
    rows = [
        "chunk_index\theading\ttoken_count\tstart_offset\tend_offset\toverlap\tpreview"
    ]
    for chunk in plan.chunks:
        preview = " ".join(chunk.content.split())[:preview_chars]
        rows.append(
            "\t".join(
                (
                    str(chunk.chunk_index),
                    " > ".join(chunk.heading_path) or "(none)",
                    str(chunk.token_count),
                    str(chunk.start_offset),
                    str(chunk.end_offset),
                    str(chunk.metadata["overlap_tokens"]),
                    preview,
                )
            )
        )
    rows.append(
        "metrics\t"
        f"duplicate_ratio={plan.metrics.duplicate_ratio:.4f}\t"
        f"boilerplate_ratio={plan.metrics.boilerplate_ratio:.4f}\t"
        f"overlap_ratio={plan.metrics.overlap_ratio:.4f}"
    )
    return "\n".join(rows)


def _source_lines(content: str) -> tuple[_Line, ...]:
    lines: list[_Line] = []
    cursor = 0
    for raw_line in content.splitlines(keepends=True):
        stripped = raw_line.strip()
        if stripped:
            leading = len(raw_line) - len(raw_line.lstrip())
            start = cursor + leading
            lines.append(_Line(start=start, end=start + len(stripped), text=stripped))
        cursor += len(raw_line)
    if cursor < len(content):
        stripped = content[cursor:].strip()
        if stripped:
            leading = len(content[cursor:]) - len(content[cursor:].lstrip())
            start = cursor + leading
            lines.append(_Line(start=start, end=start + len(stripped), text=stripped))
    return tuple(lines)


def _heading(
    text: str, source_type: ResearchDocumentSourceType, position: int
) -> tuple[int, str] | None:
    markdown = _MARKDOWN_HEADING.match(text)
    if markdown:
        return len(markdown.group(1)), markdown.group(2).strip()
    if position == 0 and len(text) <= 100:
        return 1, text
    if source_type in {
        ResearchDocumentSourceType.HOMEPAGE,
        ResearchDocumentSourceType.ABOUT,
        ResearchDocumentSourceType.PRODUCTS,
        ResearchDocumentSourceType.CAPABILITIES,
        ResearchDocumentSourceType.NEWS,
        ResearchDocumentSourceType.PDF,
    }:
        words = text.split()
        if (
            1 <= len(words) <= 10
            and len(text) <= 80
            and text[-1:] not in ".!?。！？:;"
            and not text.startswith(("-", "*", "•"))
        ):
            return 2, text
    return None


def _is_boilerplate(normalized: str) -> bool:
    return len(normalized) <= 180 and any(hint in normalized for hint in _BOILERPLATE_HINTS)


def _section_type(
    source_type: ResearchDocumentSourceType, page_number: int | None
) -> str:
    if source_type is ResearchDocumentSourceType.PDF:
        return "pdf_page" if page_number is not None else "pdf_text"
    return f"{source_type.value}_section"


def _sentence_end_token_indexes(
    content: str, tokens: tuple[TokenSpan, ...]
) -> tuple[int, ...]:
    indexes: list[int] = []
    for index, token in enumerate(tokens, start=1):
        if token.text in _SENTENCE_END:
            indexes.append(index)
            continue
        if index < len(tokens) and "\n\n" in content[token.end : tokens[index].start]:
            indexes.append(index)
    if not indexes or indexes[-1] != len(tokens):
        indexes.append(len(tokens))
    return tuple(indexes)


def _choose_end_index(
    sentence_ends: tuple[int, ...],
    *,
    start_index: int,
    target_end: int,
    hard_end: int,
) -> int:
    after_target = [
        index for index in sentence_ends if target_end <= index <= hard_end
    ]
    if after_target:
        return after_target[0]
    before_target = [
        index for index in sentence_ends if start_index < index < target_end
    ]
    return before_target[-1] if before_target else hard_end


def _choose_overlap_start(
    sentence_ends: tuple[int, ...],
    *,
    current_start: int,
    end_index: int,
    overlap_tokens: int,
) -> int:
    if overlap_tokens == 0:
        return end_index
    desired = max(current_start + 1, end_index - overlap_tokens)
    sentence_starts = (0, *sentence_ends[:-1])
    candidates = [index for index in sentence_starts if desired <= index < end_index]
    next_start = candidates[0] if candidates else desired
    return max(current_start + 1, next_start)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
