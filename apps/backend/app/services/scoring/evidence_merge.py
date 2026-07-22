"""Conservative one-signal-per-dimension evidence selection for scoring."""

from dataclasses import dataclass

from app.domain.import_evidence.models import ImportEvidenceScoringProjection, QualityStatus
from app.domain.values import SourceReference

_ALIASES = {
    "cargo_value": "cargo_value_potential",
    "growth": "growth_signal",
    "complexity": "logistics_complexity",
}


@dataclass(frozen=True)
class ScoringEvidenceMergeResult:
    signals: tuple[str, ...]
    sources: tuple[SourceReference, ...]
    selection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _Candidate:
    rendered: str
    kind: str
    origin: str
    priority: int
    quality_score: float
    freshness: float


class ScoringEvidenceMergePolicy:
    """Manual > high-quality customs > verified research > other evidence."""

    def merge(
        self,
        *,
        company_signals: tuple[str, ...],
        company_sources: tuple[SourceReference, ...],
        import_projection: ImportEvidenceScoringProjection | None,
    ) -> ScoringEvidenceMergeResult:
        projection = import_projection or ImportEvidenceScoringProjection()
        research = set(projection.research_signals)
        by_kind: dict[str, list[_Candidate]] = {}
        unknown: list[str] = []
        for position, signal in enumerate(company_signals):
            kind = _canonical_kind(signal)
            if kind is None:
                if signal not in unknown:
                    unknown.append(signal)
                continue
            origin = "website_research" if signal in research else "manual_or_existing"
            priority = 200 if origin == "website_research" else 400
            by_kind.setdefault(kind, []).append(
                _Candidate(signal, kind, origin, priority, 100.0, -float(position))
            )
        for projected_signal in projection.signals:
            priority = 320 if projected_signal.quality_status is QualityStatus.VERIFIED else 300
            by_kind.setdefault(projected_signal.signal_kind, []).append(
                _Candidate(
                    projected_signal.rendered_signal,
                    projected_signal.signal_kind,
                    "import_evidence",
                    priority,
                    projected_signal.quality_score,
                    projected_signal.created_at.timestamp(),
                )
            )

        selected: list[str] = []
        reasons: list[str] = []
        for kind, candidates in by_kind.items():
            winner = max(
                candidates,
                key=lambda row: (row.priority, row.quality_score, row.freshness),
            )
            selected.append(winner.rendered)
            if len(candidates) > 1 or winner.origin == "import_evidence":
                origins = ", ".join(sorted({row.origin for row in candidates}))
                reasons.append(
                    f"{kind}: selected {winner.origin} by evidence priority "
                    f"from [{origins}]; the dimension is scored once"
                )

        sources = list(company_sources)
        seen = {(source.source, source.reference) for source in sources}
        for projected_signal in projection.signals:
            reference = f"urn:import-evidence:aggregate:{projected_signal.aggregate_id}"
            key = ("import_evidence", reference)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                SourceReference(
                    source="import_evidence",
                    reference=reference,
                    retrieved_at=projected_signal.created_at,
                )
            )
        return ScoringEvidenceMergeResult(
            signals=tuple((*selected, *unknown)),
            sources=tuple(sources),
            selection_reasons=tuple(reasons),
        )


def _canonical_kind(signal: str) -> str | None:
    if ":" not in signal:
        return None
    kind = signal.split(":", 1)[0].strip().lower()
    canonical = _ALIASES.get(kind, kind)
    return canonical if canonical else None
