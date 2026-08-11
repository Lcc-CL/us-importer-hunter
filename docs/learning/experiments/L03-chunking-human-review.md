# L03 — Human Chunking Review

日期：2026-08-10
状态：**WAITING FOR LEO CHUNK REVIEW**
范围：R2a.1 人工 Chunk Quality 校准；不是 Retriever evaluation。

## Review Rules

- 候选 chunk 来自 `apps/backend/tests/fixtures/rag/chunking_documents.v0.json`，稳定 ID 与 `L03-chunking-relevance-template.jsonl` 交叉核对。
- R1 的 10 条 ingestion fixtures 用于确认 source provenance、duplicate、quarantine、oversize 与 cleaned structure 场景仍被覆盖；它们不是人工 relevance label。
- 候选顺序是文档内 `chunk_index` 顺序，不是 retrieval ranking。
- 不计算 Recall@K、MRR 或 nDCG；当前没有 Retriever。
- Leo 只填写每题末尾四个字段。可在 `LEO_BOUNDARY_PROBLEM` 使用：
  - `CHUNK_TOO_SMALL_OR_FRAGMENTED`
  - `CHUNK_TOO_LARGE_OR_MIXED`
- 若内容预览被截断，以 `offset` 定位原始 fixture；不要根据预览省略号推断 relevance。

## Calibration Targets

| Metric | R2a.1 target | Current status |
|---|---:|---|
| `question_evidence_coverage` | `>= 90%` | `PENDING_HUMAN_LABEL` |
| `boundary_break_count` | `0` obvious breaks | `PENDING_HUMAN_LABEL` |
| `chunks_required_per_answer` | usually `1–3` | `PENDING_HUMAN_LABEL` |
| `hard_limit_violation` | `0` | automatic: `0` |
| `offset_roundtrip_error` | `0` | automatic: `0` |
| `stable_identity_rate` | `100%` | automatic: `100%` |
| `boilerplate_ratio` | `< 10%` aggregate calibration target | automatic raw aggregate: `0.15%` |
| `duplicate_ratio` | observe and minimize | automatic raw aggregate: `0.13%` |
| `overlap_ratio` | `< 15%` unnecessary overlap | automatic raw overlap: `11.14%`; necessity is `PENDING_HUMAN_LABEL` |

---

## Q01 — 公司主营产品是什么？

- `question_id`: `Q01_MAIN_PRODUCTS`
- `company`: `Acme Industrial`
- `document`: `repeated-footer-nav` / `10000000-0000-0000-0000-000000000009`
- `source_url`: `https://fixture.example/repeated-footer-nav`
- `review_focus`: 主营产品事实是否被保留，同时 footer、CTA 与重复卡片是否没有污染证据。

### Candidate Chunk 1

- `chunk_id`: `2daad9a3-5b68-5e72-a0b4-70e623cad4c4`
- `chunk_index`: `0`
- `heading_path`: `Company Overview`
- `token_count`: `11`
- `offset`: `[0, 79)`

```text
# Company Overview
Acme imports industrial fasteners for regional distribution.
```

### Candidate Chunk 2

- `chunk_id`: `d26f680f-dbe5-5247-843f-4c7788358d85`
- `chunk_index`: `1`
- `heading_path`: `Company Overview > Product card: stainless bolts`
- `token_count`: `5`
- `offset`: `[96, 125)`

```text
Product card: stainless bolts
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q02 — 公司是否与 fitness equipment 相关？

- `question_id`: `Q02_FITNESS_EQUIPMENT_RELEVANCE`
- `company`: `Acme Industrial`
- `document`: `oversized-section` / `10000000-0000-0000-0000-000000000008`
- `source_url`: `https://fixture.example/oversized-section`
- `review_focus`: 判断当前 chunk 是否给出足够业务语境来支持相关或不相关结论，并检查重复 oversized 内容是否产生噪声。

### Candidate Chunk 1

- `chunk_id`: `0d5af75e-23ba-518b-944a-e90ae81b7c7b`
- `chunk_index`: `0`
- `heading_path`: `Industrial Catalog`
- `token_count`: `507`
- `offset`: `[0, 4010)`

```text
# Industrial Catalog
The catalog lists corrosion resistant components for construction and manufacturing customers.
The same sentence continues repeatedly in this fixture to exercise oversized-section splitting.
[preview truncated; inspect the recorded offset for the exact source span]
```

### Candidate Chunk 2

- `chunk_id`: `a9546ade-0385-5876-9d40-c317f775fa4c`
- `chunk_index`: `1`
- `heading_path`: `Industrial Catalog`
- `token_count`: `504`
- `offset`: `[3441, 7430)`

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
The same sentence continues repeatedly in this fixture.
[preview truncated; leading span overlaps chunk 0]
```

### Candidate Chunk 3

- `chunk_id`: `3cbbc09d-4c88-541e-aeb2-fe670a4f5ee0`
- `chunk_index`: `2`
- `heading_path`: `Industrial Catalog`
- `token_count`: `504`
- `offset`: `[6861, 10850)`

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
The same sentence continues repeatedly in this fixture.
[preview truncated; leading span overlaps chunk 1]
```

### Candidate Chunk 4

- `chunk_id`: `87f8d4d7-7089-5724-8389-91656c1f384b`
- `chunk_index`: `3`
- `heading_path`: `Industrial Catalog`
- `token_count`: `504`
- `offset`: `[10281, 14270)`

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
The same sentence continues repeatedly in this fixture.
[preview truncated; leading span overlaps chunk 2]
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q03 — 是否存在 importer / distributor / retailer 证据？

- `question_id`: `Q03_IMPORT_DISTRIBUTION_EVIDENCE`
- `company`: `Acme Industrial`
- `document`: `long-paragraph` / `10000000-0000-0000-0000-000000000005`
- `source_url`: `https://fixture.example/long-paragraph`
- `review_focus`: 判断 importer 行为事实是否集中在少量 chunk，还是被重复内容切成过多碎片。

### Candidate Chunk 1

- `chunk_id`: `c00b7385-45db-5b35-9ba3-ec5d65a199f0`
- `chunk_index`: `0`
- `heading_path`: `Import Operations`
- `token_count`: `507`
- `offset`: `[0, 3691)`

```text
# Import Operations
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
The same sentence continues repeatedly in this fixture.
[preview truncated]
```

### Candidate Chunk 2

- `chunk_id`: `6b783be7-0503-5a4d-b773-9609d0b75d7b`
- `chunk_index`: `1`
- `heading_path`: `Import Operations`
- `token_count`: `504`
- `offset`: `[3182, 6853)`

```text
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
The same sentence continues repeatedly in this fixture.
[preview truncated; 70 leading tokens overlap chunk 0]
```

### Candidate Chunk 3

- `chunk_id`: `05be6072-e616-5649-9d29-55144ec3d49b`
- `chunk_index`: `2`
- `heading_path`: `Import Operations`
- `token_count`: `504`
- `offset`: `[6344, 10015)`

```text
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
The same sentence continues repeatedly in this fixture.
[preview truncated; 70 leading tokens overlap chunk 1]
```

### Candidate Chunk 4

- `chunk_id`: `29e63226-a7db-50f2-a951-99e1cf4beb28`
- `chunk_index`: `3`
- `heading_path`: `Import Operations`
- `token_count`: `504`
- `offset`: `[9506, 13177)`

```text
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
The same sentence continues repeatedly in this fixture.
[preview truncated; 70 leading tokens overlap chunk 2]
```

### Candidate Chunk 5

- `chunk_id`: `e08a2235-2487-591d-ba93-f2f9c5af9f17`
- `chunk_index`: `4`
- `heading_path`: `Import Operations`
- `token_count`: `224`
- `offset`: `[12668, 14299)`

```text
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
The same sentence continues to the end of this fixture.
[preview truncated; 70 leading tokens overlap chunk 3]
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q04 — 是否存在中国供应链或进口来源证据？

- `question_id`: `Q04_CHINA_SUPPLY_CHAIN_EVIDENCE`
- `company`: `Acme Industrial`
- `document`: `about-page` / `10000000-0000-0000-0000-000000000002`
- `source_url`: `https://fixture.example/about-page`
- `review_focus`: 中国来源事实是否与公司身份及 supply-network heading 保持在可引用边界内。

### Candidate Chunk 1

- `chunk_id`: `4ec0891b-2262-5b87-9683-46302ebc0232`
- `chunk_index`: `0`
- `heading_path`: `About Acme`
- `token_count`: `33`
- `offset`: `[0, 189)`

```text
# About Acme
Acme was founded in 1998 and operates distribution centers in California and Texas.

## Supply Network
The company sources steel components from factories in China and Vietnam.
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q05 — 哪些产品或 HS 信息支持目标匹配？

- `question_id`: `Q05_PRODUCT_OR_HS_TARGET_MATCH`
- `company`: `Acme Industrial`
- `document`: `product-page` / `10000000-0000-0000-0000-000000000003`
- `source_url`: `https://fixture.example/product-page`
- `review_focus`: 产品类别是否足以支持目标匹配；若页面没有 HS 信息，也应由 Leo 明确记录证据边界。

### Candidate Chunk 1

- `chunk_id`: `8abf37e9-47b1-5864-8b49-e6e1e7e92d1e`
- `chunk_index`: `0`
- `heading_path`: `Products`
- `token_count`: `18`
- `offset`: `[0, 112)`

```text
# Products
## Fasteners
Bolts
Screws
Washers

## Material Handling
Pallet jacks
Industrial carts
Warehouse racks
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q06 — 公司业务角色是什么？

- `question_id`: `Q06_COMPANY_BUSINESS_ROLE`
- `company`: `Acme Industrial`
- `document`: `homepage` / `10000000-0000-0000-0000-000000000001`
- `source_url`: `https://fixture.example/homepage`
- `review_focus`: sourcing、distribution 与所服务客户类型是否处于同一可解释 retrieval unit。

### Candidate Chunk 1

- `chunk_id`: `abdf3398-2b90-5196-b517-9cad40c52ffe`
- `chunk_index`: `0`
- `heading_path`: `Acme Industrial`
- `token_count`: `27`
- `offset`: `[0, 166)`

```text
# Acme Industrial
Global sourcing and distribution for industrial fasteners.

## Markets
We serve importers, distributors, and manufacturers across the United States.
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q07 — 是否存在明显非目标业务？

- `question_id`: `Q07_OBVIOUS_NON_TARGET_BUSINESS`
- `company`: `Acme Industrial`
- `document`: `very-short-sections` / `10000000-0000-0000-0000-000000000007`
- `source_url`: `https://fixture.example/very-short-sections`
- `review_focus`: 该 chunk 是否只包含地点、成立年份与团队规模，而不足以支持业务相关或非目标判断。

### Candidate Chunk 1

- `chunk_id`: `1575b6d9-124b-5f92-85ac-6a86db0b5b97`
- `chunk_index`: `0`
- `heading_path`: `Locations`
- `token_count`: `15`
- `offset`: `[0, 68)`

```text
# Locations
California.

## Founded
1998.

## Team
Eighty employees.
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q08 — 公司页面里的关键产品或履约能力事实是什么？

- `question_id`: `Q08_KEY_PAGE_PRODUCT_CAPABILITY_FACTS`
- `company`: `Acme Industrial`
- `document`: `heading-list` / `10000000-0000-0000-0000-000000000006`
- `source_url`: `https://fixture.example/heading-list`
- `review_focus`: 列表结构是否保留 warehousing 与 distribution 语义，且不会把短列表切成无法理解的碎片。

### Candidate Chunk 1

- `chunk_id`: `087d4224-4b0e-5aa2-8112-5559e2223b25`
- `chunk_index`: `0`
- `heading_path`: `Capabilities`
- `token_count`: `23`
- `offset`: `[0, 139)`

```text
# Capabilities
## Warehousing
- Cross-docking
- Inventory storage
- Pick and pack

## Distribution
- Retail replenishment
- Dealer delivery
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q09 — 是否有支持 Opportunity 判断的事实？

- `question_id`: `Q09_OPPORTUNITY_SUPPORTING_FACTS`
- `company`: `Acme Industrial`
- `document`: `blog-news` / `10000000-0000-0000-0000-000000000004`
- `source_url`: `https://fixture.example/blog-news`
- `review_focus`: 新设施、港口接收能力与进口产品 inland transit 事实是否足以形成可审计的 Opportunity 输入，而不是直接替代 Opportunity 判断。

### Candidate Chunk 1

- `chunk_id`: `f480fed7-390b-5782-ad26-8813b27bd6c2`
- `chunk_index`: `0`
- `heading_path`: `Acme Opens Texas Distribution Center`
- `token_count`: `32`
- `offset`: `[0, 200)`

```text
# Acme Opens Texas Distribution Center
The new facility adds receiving capacity near major Gulf ports.

## Operations Update
Acme expects shorter inland transit times for imported industrial products.
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

---

## Q10 — 某个 claim 的最佳 citation 应该是哪一个 chunk？

- `question_id`: `Q10_BEST_CITATION_FOR_FREIGHT_MODE_CLAIM`
- `company`: `Pacific Components`
- `document`: `text-pdf-pages` / `10000000-0000-0000-0000-000000000010`
- `source_url`: `https://fixture.example/text-pdf-pages`
- `claim_under_review`: `Pacific Components uses ocean freight for regular replenishment and air freight for urgent orders.`
- `review_focus`: 在两个 PDF page chunks 中选择最直接、最小且足够的 citation target。

### Candidate Chunk 1

- `chunk_id`: `040d7eb2-187c-5585-b660-3e6d029d290c`
- `chunk_index`: `0`
- `heading_path`: `Supplier Overview`
- `token_count`: `11`
- `offset`: `[11, 85)`

```text
# Supplier Overview
Pacific Components sources precision parts from Japan.
```

### Candidate Chunk 2

- `chunk_id`: `12628577-8370-53be-b73c-5d731531c7ef`
- `chunk_index`: `1`
- `heading_path`: `Logistics`
- `token_count`: `17`
- `offset`: `[98, 201)`

```text
# Logistics
The company uses ocean freight for regular replenishment and air freight for urgent orders.
```

`LEO_RELEVANT:`

`LEO_NOT_RELEVANT:`

`LEO_BOUNDARY_PROBLEM:`

`LEO_NOTES:`

## Leo Completion Check

- [ ] 10 个问题均填写 relevant / not relevant。
- [ ] 每题检查 boundary problem，不只检查答案正确性。
- [ ] 记录每题需要的最小 chunk 数量。
- [ ] 标出必须读取大量碎片的题为 `CHUNK_TOO_SMALL_OR_FRAGMENTED`。
- [ ] 标出单个 chunk 混合过多独立主题的题为 `CHUNK_TOO_LARGE_OR_MIXED`。
- [ ] 完成后再计算 human-dependent metrics；在此之前保持 `PENDING_HUMAN_LABEL`。
