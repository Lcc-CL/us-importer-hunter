# ADR: Import Entity Resolution

**Status**: Proposed · **Date**: 2026-07-21

## Context

Different providers name the same company differently. "Pacific Home Goods Inc."
in ImportYeti may be "PACIFIC HOME GOODS INC." in CID or "Pacific Home Goods"
in a BOL consignee field. We must match these to our known Company aggregate
without false merges.

## Decision

Three-tier deterministic matching. No LLM for entity resolution.

### Tier 1: Strong Match (auto_match)
- Same domain (normalized: lowercase, remove www, trim)
- Same normalized address (street + city + state + zip)
- Same provider-specific ID from a previously matched record
- Same phone number or registration ID

### Tier 2: Composite Match (auto_match)
- Normalized company name (lowercase, remove Inc/LLC/Corp/Ltd suffixes,
  collapse whitespace, remove punctuation)
- AND city + state match
- OR domain match with name similarity ≥ 85%

### Tier 3: Fuzzy Match (needs_review)
- RapidFuzz token_set_ratio ≥ 92 AND region (state/province) matches
- Jaro-Winkler ≥ 95 AND same postal code prefix

### Thresholds
- ≥ 92 + region match → auto_match
- 80–91 + any region evidence → needs_review
- < 80 OR no region evidence → separate

## Anti-Patterns

- ❌ Matching on company name alone (false merges across states)
- ❌ LLM-based matching (non-deterministic, expensive, hard to audit)
- ❌ Merging based on similar import patterns
- ❌ Ignoring region mismatches for fuzzy matches

## Match Audit Trail

Every match stores:
- match_method (strong / composite / fuzzy)
- match_score (0-100)
- match_reasons (list of evidence strings)
- review_status (auto / confirmed / rejected)
- reviewer_id (if manually confirmed/rejected)
- matched_at timestamp

## Consequences

- Known companies with strong signals auto-match with high confidence
- Ambiguous matches are surfaced for human review, not silently merged
- Entity resolution quality feeds into EvidenceQuality.overall_confidence
  via entity_match_confidence weight
