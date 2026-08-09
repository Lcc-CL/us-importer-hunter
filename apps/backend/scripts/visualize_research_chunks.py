"""Render deterministic chunk boundaries for a fixture document."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.domain.research import (
    ResearchDocument,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
    research_document_content_hash,
)
from app.services.research import DeterministicDocumentChunker, render_chunk_visualization

DEFAULT_FIXTURE = Path("tests/fixtures/rag/chunking_documents.v0.json")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show deterministic ResearchDocument chunk boundaries."
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--case", required=True, help="Fixture case id")
    return parser.parse_args()


def _content(case: dict[str, Any]) -> str:
    if "content" in case:
        return str(case["content"]).strip()
    return (
        str(case.get("prefix", ""))
        + str(case["repeat_sentence"]) * int(case["repeat_count"])
    ).strip()


def _document(case: dict[str, Any]) -> ResearchDocument:
    content = _content(case)
    return ResearchDocument(
        document_id=UUID(str(case["document_id"])),
        company_id=UUID(str(case["company_id"])),
        research_run_id=UUID("30000000-0000-0000-0000-000000000001"),
        source_url=f"https://fixture.example/{case['id']}",
        canonical_url=f"https://fixture.example/{case['id']}",
        final_url=f"https://fixture.example/{case['id']}",
        source_type=ResearchDocumentSourceType(str(case["source_type"])),
        title=None,
        content=content,
        content_hash=research_document_content_hash(content),
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=ResearchDocumentStatus.READY,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="fixture-v1",
        supersedes_document_id=None,
        duplicate_of_document_id=None,
        is_current=True,
        superseded_at=None,
        metadata={"fixture_id": case["id"]},
    )


def main() -> None:
    args = _arguments()
    cases = json.loads(args.fixture.read_text())
    case = next((item for item in cases if item["id"] == args.case), None)
    if case is None:
        raise SystemExit(f"unknown fixture case: {args.case}")
    plan = DeterministicDocumentChunker().chunk(_document(case))
    print(f"chunker_version={plan.chunker_version}")
    print(f"tokenizer_profile={plan.tokenizer_profile}")
    print(render_chunk_visualization(plan))


if __name__ == "__main__":
    main()
