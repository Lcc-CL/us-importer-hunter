# L03 — Chunk Boundary Review

日期：2026-08-10
状态：**WAITING FOR LEO VISUAL REVIEW**
Chunker：`structure-recursive-v1:e89d30e35ee3`
Tokenizer profile：`unicode-lexical-v1`

## How To Read This Report

```text
document
└── section boundary
    └── chunk boundary
        ├── sentence boundary used
        ├── overlap region, if any
        └── hard split, only when no safe sentence boundary exists
```

标记：

- `§`：source section/page boundary。
- `│ CHUNK`：emitted retrieval unit。
- `SENTENCE_SAFE`：oversized section 在句号边界切分。
- `OVERLAP [start,end)`：相邻 chunks 共享的原文 offset span。
- `HARD_SPLIT`：没有安全 sentence boundary 时在 token boundary 强切。
- `BOILERPLATE_REMOVED`：deterministic boilerplate filter 丢弃的 source line。
- `DUPLICATE_REMOVED`：同一文档内重复 normalized line 被丢弃。
- `MERGED`：相邻短 section 在 target 内合成一个 chunk。

本报告只展示 deterministic plan。它不声称 chunk relevant，也不计算 retrieval metrics。

Leo 不需要阅读 chunker 内部代码。先看下面 5 张卡，只判断切口是否自然；后面的 fixture 细节仅供需要时查证。

## Leo Quick Boundary Cards

### Card A — Heading Boundary Was Kept Inside One Chunk

Document：`product-page`

```text
[Previous Chunk]
NONE — document start

──────── CUT: DOCUMENT START ────────

[Current Chunk]
chunk 8abf37e9-47b1-5864-8b49-e6e1e7e92d1e

# Products
## Fasteners
Bolts / Screws / Washers

## Material Handling
Pallet jacks / Industrial carts / Warehouse racks

──────── CUT: DOCUMENT END ────────

[Next Chunk]
NONE — document end
```

- `heading boundary`: **YES**, `Fasteners` 与 `Material Handling` headings 保留在 content 中，但被 merge 到同一 chunk。
- `sentence boundary`: **NOT USED FOR A CHUNK CUT**。
- `hard split`: **NO**。
- `overlap`: **0**。
- Leo 判断点：两个产品主题放在一起是有用上下文，还是 `CHUNK_TOO_LARGE_OR_MIXED`？

### Card B — Sentence Boundary With Overlap

Document：`long-paragraph`，聚焦 `chunk 1`

```text
[Previous Chunk]
chunk 0 · offsets [0,3691)
... Acme coordinates monthly container imports from Asian suppliers
through multiple United States ports.

──────── CUT: SENTENCE BOUNDARY ────────
OVERLAP [3182,3691) · 70 tokens
HARD SPLIT: NO

[Current Chunk]
chunk 1 · offsets [3182,6853)
Acme coordinates monthly container imports from Asian suppliers
through multiple United States ports. ...

──────── CUT: SENTENCE BOUNDARY ────────
OVERLAP [6344,6853) · 70 tokens
HARD SPLIT: NO

[Next Chunk]
chunk 2 · offsets [6344,10015)
Acme coordinates monthly container imports from Asian suppliers
through multiple United States ports. ...
```

- `heading boundary`: **NO**, 三块都属于 `Import Operations`。
- `sentence boundary`: **YES**, 两侧都在完整句号后切分。
- `hard split`: **NO**。
- `overlap`: **YES**, current 的开头重复 previous 末尾，next 的开头重复 current 末尾。
- Leo 判断点：overlap 是否保留必要语境，还是因为重复事实制造 retrieval noise？

### Card C — Oversized Catalog Cut

Document：`oversized-section`，聚焦 `chunk 2`

```text
[Previous Chunk]
chunk 1 · offsets [3441,7430)
... corrosion resistant components for construction and manufacturing customers.

──────── CUT: SENTENCE BOUNDARY ────────
OVERLAP [6861,7430) · 72 tokens
HARD SPLIT: NO

[Current Chunk]
chunk 2 · offsets [6861,10850)
The catalog lists corrosion resistant components for construction
and manufacturing customers. ...

──────── CUT: SENTENCE BOUNDARY ────────
OVERLAP [10281,10850) · 72 tokens
HARD SPLIT: NO

[Next Chunk]
chunk 3 · offsets [10281,14270)
The catalog lists corrosion resistant components for construction
and manufacturing customers. ...
```

- `heading boundary`: **NO**, 三块都属于 `Industrial Catalog`。
- `sentence boundary`: **YES**。
- `hard split`: **NO**。
- `overlap`: **YES**, 每个 overlap 是完整句子组合，未超过 configured max 80。
- Leo 判断点：边界本身是否自然，以及重复 catalog 语言是否让多个 chunks 没有独立价值。

### Card D — Filtered Lines Between Two Short Chunks

Document：`repeated-footer-nav`，聚焦 `chunk 1`

```text
[Previous Chunk]
chunk 0 · offsets [0,79)
# Company Overview
Acme imports industrial fasteners for regional distribution.

──────── CUT: FILTERED SOURCE GAP ────────
BOILERPLATE REMOVED: Request a quote
HEADING/LINE BOUNDARY: Product card
OVERLAP: 0
HARD SPLIT: NO

[Current Chunk]
chunk 1 · offsets [96,125)
Product card: stainless bolts

──────── CUT: DOCUMENT END AFTER FILTERING ────────
DUPLICATE REMOVED: repeated product-card line
BOILERPLATE REMOVED: All rights reserved

[Next Chunk]
NONE — document end
```

- `heading boundary`: **YES**, product-card line becomes the current heading context。
- `sentence boundary`: **NO CHUNK SPLIT REQUIRED**。
- `hard split`: **NO**。
- `overlap`: **0**。
- Leo 判断点：5-token product-card chunk 是有效 atomic fact、碎片、boilerplate，还是应该与 previous 合并？

### Card E — PDF Page And Heading Boundary

Document：`text-pdf-pages`，聚焦 `chunk 1`

```text
[Previous Chunk]
chunk 0 · page 1 · offsets [11,85)
# Supplier Overview
Pacific Components sources precision parts from Japan.

──────── CUT: PAGE 2 + HEADING BOUNDARY ────────
PAGE MARKER: [[Page 2]] is not emitted
OVERLAP: 0
HARD SPLIT: NO

[Current Chunk]
chunk 1 · page 2 · offsets [98,201)
# Logistics
The company uses ocean freight for regular replenishment
and air freight for urgent orders.

──────── CUT: DOCUMENT END ────────

[Next Chunk]
NONE — document end
```

- `heading boundary`: **YES**, `Supplier Overview` → `Logistics`。
- `sentence boundary`: current content itself is complete, but the chunk cut is driven by page/heading structure。
- `hard split`: **NO**。
- `overlap`: **0**。
- Leo 判断点：page-local chunks 是否提升 best-citation precision，还是需要跨页 context？

### Hard Split Status

```text
HARD SPLIT OBSERVED IN THE 10 FIXTURES: NO
```

本轮所有 oversized cuts 都找到了安全 sentence boundary。这个结果只描述当前 fixtures，不代表未来文档永远不会出现 hard split。

## Inputs Used

### R1 Ingestion Fixtures — 10 Cases

| Fixture | Boundary/provenance purpose in R2a.1 |
|---|---|
| `same-url-same-content` | idempotent source version scenario |
| `same-url-changed-content` | immutable new document version scenario |
| `different-url-identical-content` | duplicate content keeps separate source provenance |
| `same-content-cross-company` | company scope remains isolated |
| `tracking-query-canonicalization` | stable canonical source identity |
| `redirect-final-url` | final URL provenance retained |
| `failed-fetch` | no document, therefore no chunk |
| `quarantined-malicious-content` | quarantined document is ineligible for chunking |
| `oversized-document` | rejected before corpus/chunking |
| `heading-list-structure` | cleaned heading/list structure reaches chunker |

### R2a Chunking Fixtures — 10 Documents

全部 10 个 fixtures 已运行：

```bash
cd apps/backend
uv run python scripts/visualize_research_chunks.py --case <fixture-id>
```

输出合计：`10 documents → 19 chunks`。

## Automatic Aggregate Snapshot

| Metric | Result |
|---|---:|
| source tokens | `3,981` |
| emitted tokens | `4,454` |
| hard token violations | `0` |
| offset roundtrip errors | `0` |
| stable rerun chunk identities | `19 / 19 = 100%` |
| duplicate tokens removed | `5` |
| boilerplate tokens removed | `6` |
| overlap tokens emitted | `496` |
| aggregate duplicate ratio | `0.13%` |
| aggregate boilerplate ratio | `0.15%` |
| aggregate raw overlap ratio | `11.14%` |
| unnecessary overlap ratio | `PENDING_HUMAN_LABEL` |

## Detailed Fixture Appendix

### 1. `homepage`

```text
document 10000000-0000-0000-0000-000000000001
source_url https://fixture.example/homepage
§ H1: Acme Industrial                 [offset 0]
§ H2: Markets                         [short adjacent section]
└── MERGED: both source sections fit below target
    │ CHUNK 0  abdf3398-2b90-5196-b517-9cad40c52ffe
    │ offsets [0,166) · 27 tokens · overlap 0
    │ heading_path: Acme Industrial
    └── complete structural chunk; no split
```

- Section boundary is preserved in content and `merged_heading_paths` even though one chunk is emitted.
- Sentence boundary is not used as a split because the complete merged section is below hard max.
- `HARD_SPLIT`: none.
- `BOILERPLATE_REMOVED`: none.
- `DUPLICATE_REMOVED`: none.

### 2. `about-page`

```text
document 10000000-0000-0000-0000-000000000002
source_url https://fixture.example/about-page
§ H1: About Acme                      [offset 0]
§ H2: Supply Network                  [short adjacent section]
└── MERGED: company facts + supply-network facts fit below target
    │ CHUNK 0  4ec0891b-2262-5b87-9683-46302ebc0232
    │ offsets [0,189) · 33 tokens · overlap 0
    │ heading_path: About Acme
    └── complete structural chunk; no split
```

- Leo should inspect whether mixing founding/location facts with sourcing facts is useful context or `CHUNK_TOO_LARGE_OR_MIXED`.
- `HARD_SPLIT`: none; `BOILERPLATE_REMOVED`: none; `DUPLICATE_REMOVED`: none.

### 3. `product-page`

```text
document 10000000-0000-0000-0000-000000000003
source_url https://fixture.example/product-page
§ H1: Products
§ H2/list group: Fasteners → Bolts / Screws / Washers
§ H2/list group: Material Handling → Pallet jacks / Industrial carts / Warehouse racks
└── MERGED: all short product groups fit below target
    │ CHUNK 0  8abf37e9-47b1-5864-8b49-e6e1e7e92d1e
    │ offsets [0,112) · 18 tokens · overlap 0
    │ heading_path: Products
    └── complete structural chunk; no split
```

- Structure-aware behavior keeps headings and list values together instead of cutting at a fixed character count.
- Leo should decide whether two independent product families in one small chunk are helpful context or mixed-topic noise.
- `HARD_SPLIT`: none; `BOILERPLATE_REMOVED`: none; `DUPLICATE_REMOVED`: none.

### 4. `blog-news`

```text
document 10000000-0000-0000-0000-000000000004
source_url https://fixture.example/blog-news
§ H1: Acme Opens Texas Distribution Center
§ H2: Operations Update
└── MERGED: event and stated logistics consequence fit below target
    │ CHUNK 0  f480fed7-390b-5782-ad26-8813b27bd6c2
    │ offsets [0,200) · 32 tokens · overlap 0
    │ heading_path: Acme Opens Texas Distribution Center
    └── complete structural chunk; no split
```

- The event fact and its operational consequence remain in one citation unit.
- `HARD_SPLIT`: none; `BOILERPLATE_REMOVED`: none; `DUPLICATE_REMOVED`: none.

### 5. `long-paragraph`

```text
document 10000000-0000-0000-0000-000000000005
source_url https://fixture.example/long-paragraph
§ H1: Import Operations               [one oversized section]
├── SENTENCE_SAFE
│   │ CHUNK 0 c00b7385-45db-5b35-9ba3-ec5d65a199f0
│   │ [0,3691) · 507 tokens · overlap 0
│   └── ends after a complete sentence
├── OVERLAP [3182,3691) = 70 tokens
│   │ CHUNK 1 6b783be7-0503-5a4d-b773-9609d0b75d7b
│   │ [3182,6853) · 504 tokens
│   └── ends after a complete sentence
├── OVERLAP [6344,6853) = 70 tokens
│   │ CHUNK 2 05be6072-e616-5649-9d29-55144ec3d49b
│   │ [6344,10015) · 504 tokens
│   └── ends after a complete sentence
├── OVERLAP [9506,10015) = 70 tokens
│   │ CHUNK 3 29e63226-a7db-50f2-a951-99e1cf4beb28
│   │ [9506,13177) · 504 tokens
│   └── ends after a complete sentence
└── OVERLAP [12668,13177) = 70 tokens
    │ CHUNK 4 e08a2235-2487-591d-ba93-f2f9c5af9f17
    │ [12668,14299) · 224 tokens
    └── final complete sentence span
```

- Why these cuts: the target is 500 tokens; the chunker chooses the nearest safe sentence end before hard max 900.
- Why overlap exists: only this oversized source section is recursively split; complete structural chunks receive no overlap.
- Human question: because the fixture repeats one fact, are chunks 1–4 unnecessary retrieval noise even though their boundaries are sentence-safe?
- `HARD_SPLIT`: none observed; every emitted slice uses a sentence boundary.
- Per-document raw overlap ratio: `12.48%`.

### 6. `heading-list`

```text
document 10000000-0000-0000-0000-000000000006
source_url https://fixture.example/heading-list
§ H1: Capabilities
§ H2/list group: Warehousing
§ H2/list group: Distribution
└── MERGED: related short capability groups fit below target
    │ CHUNK 0 087d4224-4b0e-5aa2-8112-5559e2223b25
    │ offsets [0,139) · 23 tokens · overlap 0
    │ heading_path: Capabilities
    └── heading/list structure remains readable
```

- No sentence split is needed; line and heading structure provide the boundaries.
- `HARD_SPLIT`: none; `BOILERPLATE_REMOVED`: none; `DUPLICATE_REMOVED`: none.

### 7. `very-short-sections`

```text
document 10000000-0000-0000-0000-000000000007
source_url https://fixture.example/very-short-sections
§ H1: Locations → California.
§ H2: Founded → 1998.
§ H2: Team → Eighty employees.
└── MERGED: three tiny adjacent sections fit below target
    │ CHUNK 0 1575b6d9-124b-5f92-85ac-6a86db0b5b97
    │ offsets [0,68) · 15 tokens · overlap 0
    │ heading_path: Locations
    └── avoids three tiny retrieval fragments
```

- Leo should inspect the tradeoff: fewer tiny chunks versus mixing three independent company facts.
- `HARD_SPLIT`: none; `BOILERPLATE_REMOVED`: none; `DUPLICATE_REMOVED`: none.

### 8. `oversized-section`

```text
document 10000000-0000-0000-0000-000000000008
source_url https://fixture.example/oversized-section
§ H1: Industrial Catalog              [one oversized section]
├── SENTENCE_SAFE
│   │ CHUNK 0 0d5af75e-23ba-518b-944a-e90ae81b7c7b
│   │ [0,4010) · 507 tokens · overlap 0
│   └── ends after a complete sentence
├── OVERLAP [3441,4010) = 72 tokens
│   │ CHUNK 1 a9546ade-0385-5876-9d40-c317f775fa4c
│   │ [3441,7430) · 504 tokens
│   └── ends after a complete sentence
├── OVERLAP [6861,7430) = 72 tokens
│   │ CHUNK 2 3cbbc09d-4c88-541e-aeb2-fe670a4f5ee0
│   │ [6861,10850) · 504 tokens
│   └── ends after a complete sentence
└── OVERLAP [10281,10850) = 72 tokens
    │ CHUNK 3 87f8d4d7-7089-5724-8389-91656c1f384b
    │ [10281,14270) · 504 tokens
    └── ends after a complete sentence
```

- The configured overlap maximum is 80 tokens; observed overlap is 72 because full sentences are reused.
- `HARD_SPLIT`: none observed.
- Per-document raw overlap ratio: `10.70%`.
- Leo should decide whether repeated catalog language makes the chunks too repetitive even though each boundary is structurally safe.

### 9. `repeated-footer-nav`

```text
document 10000000-0000-0000-0000-000000000009
source_url https://fixture.example/repeated-footer-nav
§ H1: Company Overview
│   │ CHUNK 0 2daad9a3-5b68-5e72-a0b4-70e623cad4c4
│   │ [0,79) · 11 tokens · overlap 0
│   └── company/import fact retained
├── BOILERPLATE_REMOVED: "Request a quote"
§ product-card line
│   │ CHUNK 1 d26f680f-dbe5-5247-843f-4c7788358d85
│   │ [96,125) · 5 tokens · overlap 0
│   └── first product-card fact retained
├── DUPLICATE_REMOVED: second "Product card: stainless bolts"
└── BOILERPLATE_REMOVED: "All rights reserved"
```

- Per-document duplicate ratio: `18.52%`; this is an intentionally noisy fixture, not the aggregate corpus ratio.
- Per-document boilerplate ratio: `22.22%`; removed text is not present in emitted chunks.
- Offset gaps are expected here because filtered source lines are not copied into chunk content.
- `HARD_SPLIT`: none.

### 10. `text-pdf-pages`

```text
document 10000000-0000-0000-0000-000000000010
source_url https://fixture.example/text-pdf-pages
§ PAGE 1 marker [[Page 1]]             [not emitted as content]
§ H1: Supplier Overview
│   │ CHUNK 0 040d7eb2-187c-5585-b660-3e6d029d290c
│   │ [11,85) · 11 tokens · page_number 1
│   └── page-local supplier fact
§ PAGE 2 marker [[Page 2]]             [hard section/page boundary]
§ H1: Logistics
    │ CHUNK 1 12628577-8370-53be-b73c-5d731531c7ef
    │ [98,201) · 17 tokens · page_number 2
    └── page-local freight-mode fact
```

- Page markers establish section boundaries but are excluded from chunk content, explaining offsets `[11,85)` and `[98,201)`.
- No cross-page merge occurs even though both chunks are short.
- `HARD_SPLIT`: none; `BOILERPLATE_REMOVED`: none; `DUPLICATE_REMOVED`: none.

## Human Boundary Checklist

- [ ] Every useful fact is understandable without reading an excessive number of chunks.
- [ ] No obvious subject/object relationship is broken across a chunk edge.
- [ ] Overlap preserves context where needed rather than duplicating retrieval noise.
- [ ] Short-section merges do not mix independent topics excessively.
- [ ] PDF page boundaries improve citation precision.
- [ ] Removed boilerplate and duplicate lines do not remove business evidence.
- [ ] Any problem is copied into `L03-chunking-human-review.md` using the prescribed flags.
