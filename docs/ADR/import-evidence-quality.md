# ADR: Import Evidence Quality Scoring

**Status**: Proposed · **Date**: 2026-07-21

## Context

Not all import evidence is equally reliable. ImportYeti provides estimated
values; CID provides observed values but is annual; a single shipment record
from one source is weaker than corroborating records from two sources. The
scorer needs a quality signal to weigh evidence appropriately.

## Decision

Five-dimensional quality score per evidence signal. Weighted sum produces
`overall_confidence` (0.0–1.0).

### Dimensions

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| source_reliability | 0.30 | Provider data quality track record |
| entity_match_confidence | 0.25 | How certain we are this record belongs to this company |
| freshness_score | 0.20 | Recency of the shipment data |
| record_completeness | 0.15 | Fraction of key fields populated |
| cross_source_consistency | 0.10 | Agreement with other providers |

### Quality Grades

| Grade | Threshold | Meaning |
|-------|-----------|---------|
| HIGH | ≥ 0.80 | Strong evidence; promote to scorer |
| MEDIUM | ≥ 0.60 | Usable evidence; note confidence |
| LOW | ≥ 0.40 | Weak evidence; flag for review |
| REVIEW | < 0.40 | Insufficient; do not promote |

### Freshness Decay

- ≤ 6 months: 1.00
- ≤ 12 months: 0.85
- ≤ 18 months: 0.65
- ≤ 24 months: 0.45
- > 24 months: 0.20

### Completeness (fields present / total key fields)
Key fields: importer_name, shipper_name, country_of_origin, arrival_date,
master_bol or house_bol, weight_kg or teu, hs_codes, goods_description.

### Cross-Source Consistency
- 2+ providers agree on importer + origin → 1.00
- 1 provider only → 0.50
- Providers conflict on origin country → 0.30

## Anti-Patterns

- ❌ Quality score substituting for business matching score
- ❌ Estimated values treated as observed
- ❌ Missing fields treated as zero (vs. unknown)
- ❌ Freshness penalty applied to annual aggregate data (CID)

## Consequences

- Scorer receives confidence-weighted signals
- Low-quality evidence is visible but doesn't inflate scores
- Quality breakdown is auditable per-signal
- Reviewer can override quality grades with audit trail
