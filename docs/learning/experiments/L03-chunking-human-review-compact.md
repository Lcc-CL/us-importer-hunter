# L03 — Human Chunking Review Compact

日期：2026-08-10
状态：**R2A FINAL EVALUATION COMPLETE**
预计 Review 时间：**20–30 分钟**

> 本文件作为 Human Ground Truth 存储记录。Leo 的实际逐题阅读入口是
> `L03-leo-review-handoff.md`；字段名和 enum 保持英文，中文含义在 handoff 中展示。

## Leo Review Checklist

Leo 只需要判断：

1. 这个 Chunk 能否回答 Question？
2. 重要事实有没有被切断？
3. 完整回答最少需要几个 Chunk？
4. `<50` token Chunk 是有效事实还是碎片？

填写规则：

- 每个 candidate 只勾选自己的 `LEO_RELEVANT` 与 `LEO_BOUNDARY_PROBLEM`。
- 每题填写 `MIN_CHUNKS_REQUIRED` 与 `LEO_NOTES`。
- 不需要计算 Recall@K、MRR 或 nDCG；当前没有 Retriever。
- 若边界明显有问题，可在 Notes 写：`CHUNK_TOO_SMALL_OR_FRAGMENTED` 或 `CHUNK_TOO_LARGE_OR_MIXED`。
- Q1–Q10 checkbox 均记录 Leo 已确认的 Human Ground Truth；禁止生成 Q11。

## 标签中文说明

- `RELEVANT`：直接相关
- `PARTIALLY_RELEVANT`：部分相关 / 证据不完整
- `NOT_RELEVANT`：不相关
- `GOOD`：分块合理
- `BROKEN_BEFORE`：前文被错误截断
- `BROKEN_AFTER`：后文被错误截断
- `BROKEN_BOTH`：前后均被错误截断
- `NOT_APPLICABLE`：不适用
- `VALID_ATOMIC_FACT`：有效的独立事实
- `VALID_HEADING_CONTEXT`：有效标题/上下文
- `FRAGMENTED`：碎片化
- `BOILERPLATE`：模板/无效重复内容
- `SHOULD_MERGE_PREVIOUS`：建议与上一 Chunk 合并
- `SHOULD_MERGE_NEXT`：建议与下一 Chunk 合并
- `YES`：证据足够完整回答
- `PARTIAL`：只能部分回答
- `NO`：当前证据无法回答

## Human Evaluation Progress

- questions completed：`10 / 10`
- questions remaining：`0 / 10`
- next step：`R2A_FINAL_EVALUATION_AND_BASELINE`

## Final Human Metrics — RAG_CHUNKING_BASELINE_V1

- `question_evidence_coverage`（YES 或 PARTIAL）: `90.00%` (`9/10`)
- `complete_answer_rate`（YES）: `70.00%` (`7/10`)
- `partial_answer_rate`（PARTIAL）: `20.00%` (`2/10`)
- `no_answer_rate`（NO）: `10.00%` (`1/10`)
- `boundary_break_count`: `1` (`BROKEN_BEFORE` on Q1 Candidate Chunk B)
- `average_minimum_chunks_required`: `1.11`（仅统计 `9` 个 YES/PARTIAL；Q7 的 `NO` 存储值为 `0`）
- `median_minimum_chunks_required`: `1`
- `max_minimum_chunks_required`: `2`
- `short_chunk_merge_candidates`: `1`
- `valid_short_chunk_count`: `9`
- retrieval relevance distribution：`RELEVANT=13`、`PARTIALLY_RELEVANT=4`、`NOT_RELEVANT=2`
- answerability distribution：`YES=7`、`PARTIAL=2`、`NO=1`
- claim entailment distribution：`ENTAILED=1`、`NOT_ENTAILED=1`、`NOT_EVALUATED=17`
- citation sufficiency distribution：`SUFFICIENT=1`、`INSUFFICIENT=1`、`NOT_EVALUATED=17`
- labeled candidate chunks：`19 / 19`
- Q1 short chunks reviewed：`2`
- Q1 short chunks marked merge candidate：`1`
- `RETRIEVAL_REDUNDANCY_CANDIDATE`: Q2 的 4 个约 500-token chunks 高度重复
- `EVIDENCE_REDUNDANCY_OBSERVED`: Q3 的 5 个 chunks 不是 5 份独立证据
- `VALID_SHORT_CHUNK_OBSERVED`: Q4 的 33-token chunk 语义完整且保留标题上下文
- `RETRIEVAL_RELEVANT_BUT_INCOMPLETE_EVIDENCE`: Q5 应被检索，但回答必须声明缺少 HS evidence
- `CUSTOMER_ROLE != COMPANY_ROLE`: Q6 的 customer list 不能用于声称 Acme 自身就是 importer
- `RETRIEVAL_RELEVANCE != CLAIM_ENTAILMENT`: Q6 的相关 evidence 不自动支持任意生成 Claim
- `ABSENCE_OF_EVIDENCE != EVIDENCE_OF_ABSENCE`: Q7 未发现非目标业务证据不能证明不存在
- `ENTITY_RELEVANCE != QUESTION_RELEVANCE`: Q7 的正确实体事实对当前 Query 没有判别价值
- `SHORT_CHUNK != BAD_CHUNK`: Q8 的 23-token 结构化能力列表可作为独立 Retrieval Unit
- `COMPANY_FACT != OPPORTUNITY_JUDGMENT`: Q9 的 Company Facts 是 Opportunity 输入，不是评分或决策
- `CHUNK_QUALITY != QUERY_RELEVANCE`: Q10 Candidate A 是有效 Chunk，但对 freight-mode Query 不相关
- `QUERY_RELEVANCE != CLAIM_ENTAILMENT`: Q10 Candidate A 不支持待验证 Claim
- `CLAIM_ENTAILMENT != CITATION_SUFFICIENCY`: Q10 独立记录 entailment 与引用充分性
- `BEST_CITATION = MINIMAL_SUFFICIENT_EVIDENCE`: Q10 Candidate B
- evidence redundancy findings：Q2/Q3 findings 保持不变；Q8–Q10 未新增重复案例
- `unnecessary_overlap_ratio`: `PENDING_HUMAN_LABEL`

Final decision：`KEEP_CURRENT_CHUNKER`。本 baseline 不证明 production optimal；未来任何参数修改必须
与 `RAG_CHUNKING_BASELINE_V1` 对比。

## Current Automatic Snapshot — Do Not Relabel

- `hard_limit_violation`: `0`
- `offset_roundtrip_error`: `0`
- `stable_identity_rate`: `100%`
- `boilerplate_ratio`: `0.15%`
- `duplicate_ratio`: `0.13%`
- `raw_overlap_ratio`: `11.14%`

---

## Review Question 01

QUESTION: 公司主营产品是什么？
BUSINESS_INTENT: 判断网页中的产品事实是否足以支持 importer prospect qualification。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/repeated-footer-nav

### Candidate Chunk A

- `chunk_id`: `2daad9a3-5b68-5e72-a0b4-70e623cad4c4`
- `heading`: `Company Overview`
- `token_count`: `11`
- `offset`: `[0, 79)`
- `content`:

```text
# Company Overview
Acme imports industrial fasteners for regional distribution.
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_ATOMIC_FACT（有效的独立事实）
LEO_NOTES: 完整且可独立理解的公司产品事实。明确说明 Acme 进口 industrial fasteners，能够直接支持主营产品类别判断。

### Candidate Chunk B

- `chunk_id`: `d26f680f-dbe5-5247-843f-4c7788358d85`
- `heading`: `Company Overview > Product card: stainless bolts`
- `token_count`: `5`
- `offset`: `[96, 125)`
- `content`:

```text
Product card: stainless bolts
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] BROKEN_BEFORE（前文被错误截断）
LEO_SHORT_CHUNK_CLASS: [x] SHOULD_MERGE_PREVIOUS（建议与上一 Chunk 合并）
LEO_NOTES: 产品事实本身相关，但 5-token chunk 过短，且与前一 Company Overview 属于同一产品语义单元。建议与 previous chunk 合并。

ANSWERABLE_FROM_CHUNKS: [x] YES（证据足够完整回答）
MIN_CHUNKS_REQUIRED: 2
EVIDENCE_MISSING: NONE
LEO_NOTES: Q1 可完整回答。Chunk A 提供主营产品类别 industrial fasteners；Chunk B 提供具体产品 stainless bolts。主要问题不是 evidence coverage，而是 Chunk B 被切成仅 5 tokens 的孤立产品卡，与 Chunk A 属于同一语义单元，应记录为潜在 merge candidate。

---

## Review Question 02

QUESTION_ID: Q02_FITNESS_RELEVANCE

QUESTION: 公司是否与 fitness equipment 相关？
BUSINESS_INTENT: 判断 catalog chunk 是否提供足够语境支持业务相关或不相关结论。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/oversized-section

### Candidate Chunk A

- `chunk_id`: `0d5af75e-23ba-518b-944a-e90ae81b7c7b`
- `heading`: `Industrial Catalog`
- `token_count`: `507`
- `offset`: `[0, 4010)`
- `content`:

```text
# Industrial Catalog
The catalog lists corrosion resistant components for construction and manufacturing customers.
[The same complete source sentence repeats through this offset span.]
```

LEO_RELEVANT: [x] PARTIALLY_RELEVANT（部分相关 / 证据不完整）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 该分块提供建筑/制造业工业零部件业务信号，对判断公司是否属于 fitness equipment 行业有帮助，但不能单独证明公司完全不涉及健身器材。

### Candidate Chunk B

- `chunk_id`: `a9546ade-0385-5876-9d40-c317f775fa4c`
- `heading`: `Industrial Catalog`
- `token_count`: `504`
- `offset`: `[3441, 7430)`
- `content`:

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
[The same complete source sentence repeats; the leading span overlaps Candidate A.]
```

LEO_RELEVANT: [x] PARTIALLY_RELEVANT（部分相关 / 证据不完整）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 与 Candidate A 基本属于相同业务证据。具有部分相关性，但没有提供 fitness equipment 的明确正向或排除证据。

### Candidate Chunk C

- `chunk_id`: `3cbbc09d-4c88-541e-aeb2-fe670a4f5ee0`
- `heading`: `Industrial Catalog`
- `token_count`: `504`
- `offset`: `[6861, 10850)`
- `content`:

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
[The same complete source sentence repeats; the leading span overlaps Candidate B.]
```

LEO_RELEVANT: [x] PARTIALLY_RELEVANT（部分相关 / 证据不完整）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 提供建筑/制造工业组件信号，但与其他候选高度重复。没有增加足以确认或完全排除 fitness equipment 的独立证据。

### Candidate Chunk D

- `chunk_id`: `87f8d4d7-7089-5724-8389-91656c1f384b`
- `heading`: `Industrial Catalog`
- `token_count`: `504`
- `offset`: `[10281, 14270)`
- `content`:

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
[The same complete source sentence repeats; the leading span overlaps Candidate C.]
```

LEO_RELEVANT: [x] PARTIALLY_RELEVANT（部分相关 / 证据不完整）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 具有弱负向业务相关性证据，但与 A/B/C 高度重复，单独无法证明公司完全不涉及 fitness equipment。

ANSWERABLE_FROM_CHUNKS: [x] PARTIAL（只能部分回答）
MIN_CHUNKS_REQUIRED: 1
EVIDENCE_MISSING: 缺少明确的公司产品分类、完整产品目录或业务描述，无法确认是否存在 fitness equipment / gym equipment 相关产品。
LEO_NOTES: 当前 Chunk 提供建筑/制造业耐腐蚀工业组件的负向业务信号，因此对 fitness equipment 相关性判断有帮助，但证据不足以作绝对排除。4 个 Candidate Chunk 内容高度重复，其中任意 1 个已经足以支持当前 PARTIAL 判断。记录 Retrieval Redundancy 风险，但本轮不得因此自动修改 Chunker。

---

## Review Question 03

QUESTION_ID: Q03_IMPORT_DISTRIBUTION_EVIDENCE

QUESTION: 是否存在 importer / distributor / retailer 证据？
BUSINESS_INTENT: 判断 importer 行为事实是否能由少量 chunks 完整支持，而不是被拆成过多碎片。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/long-paragraph

### Candidate Chunk A

- `chunk_id`: `c00b7385-45db-5b35-9ba3-ec5d65a199f0`
- `heading`: `Import Operations`
- `token_count`: `507`
- `offset`: `[0, 3691)`
- `content`:

```text
# Import Operations
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
[The same complete source sentence repeats through this offset span.]
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 原文明确说明 Acme 每月协调来自亚洲供应商的集装箱进口，并通过多个美国港口进入美国。这属于直接 importer / import operations 行为证据。虽然当前证据没有证明 distributor 或 retailer 身份，但问题采用 importer / distributor / retailer 的 OR 语义，因此 importer 证据已经足以回答当前问题。多个 Candidate Chunk 高度重复，不得把重复 Chunk 当成多个独立证据。

### Candidate Chunk B

- `chunk_id`: `6b783be7-0503-5a4d-b773-9609d0b75d7b`
- `heading`: `Import Operations`
- `token_count`: `504`
- `offset`: `[3182, 6853)`
- `content`:

```text
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
[The same complete source sentence repeats; 70 leading tokens overlap Candidate A.]
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 原文明确说明 Acme 每月协调来自亚洲供应商的集装箱进口，并通过多个美国港口进入美国。这属于直接 importer / import operations 行为证据。虽然当前证据没有证明 distributor 或 retailer 身份，但问题采用 importer / distributor / retailer 的 OR 语义，因此 importer 证据已经足以回答当前问题。多个 Candidate Chunk 高度重复，不得把重复 Chunk 当成多个独立证据。

### Candidate Chunk C

- `chunk_id`: `05be6072-e616-5649-9d29-55144ec3d49b`
- `heading`: `Import Operations`
- `token_count`: `504`
- `offset`: `[6344, 10015)`
- `content`:

```text
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
[The same complete source sentence repeats; 70 leading tokens overlap Candidate B.]
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 原文明确说明 Acme 每月协调来自亚洲供应商的集装箱进口，并通过多个美国港口进入美国。这属于直接 importer / import operations 行为证据。虽然当前证据没有证明 distributor 或 retailer 身份，但问题采用 importer / distributor / retailer 的 OR 语义，因此 importer 证据已经足以回答当前问题。多个 Candidate Chunk 高度重复，不得把重复 Chunk 当成多个独立证据。

### Candidate Chunk D

- `chunk_id`: `29e63226-a7db-50f2-a951-99e1cf4beb28`
- `heading`: `Import Operations`
- `token_count`: `504`
- `offset`: `[9506, 13177)`
- `content`:

```text
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
[The same complete source sentence repeats; 70 leading tokens overlap Candidate C.]
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 原文明确说明 Acme 每月协调来自亚洲供应商的集装箱进口，并通过多个美国港口进入美国。这属于直接 importer / import operations 行为证据。虽然当前证据没有证明 distributor 或 retailer 身份，但问题采用 importer / distributor / retailer 的 OR 语义，因此 importer 证据已经足以回答当前问题。多个 Candidate Chunk 高度重复，不得把重复 Chunk 当成多个独立证据。

### Candidate Chunk E

- `chunk_id`: `e08a2235-2487-591d-ba93-f2f9c5af9f17`
- `heading`: `Import Operations`
- `token_count`: `224`
- `offset`: `[12668, 14299)`
- `content`:

```text
Acme coordinates monthly container imports from Asian suppliers through multiple United States ports.
[The same complete source sentence repeats to the end; 70 leading tokens overlap Candidate D.]
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] NOT_APPLICABLE（不适用）
LEO_NOTES: 原文明确说明 Acme 每月协调来自亚洲供应商的集装箱进口，并通过多个美国港口进入美国。这属于直接 importer / import operations 行为证据。虽然当前证据没有证明 distributor 或 retailer 身份，但问题采用 importer / distributor / retailer 的 OR 语义，因此 importer 证据已经足以回答当前问题。多个 Candidate Chunk 高度重复，不得把重复 Chunk 当成多个独立证据。

ANSWERABLE_FROM_CHUNKS: [x] YES（证据足够完整回答）
MIN_CHUNKS_REQUIRED: 1
EVIDENCE_MISSING: NONE
LEO_NOTES: 一个包含完整进口事实的 Chunk 已足以支持 YES。当前另外 4 个候选主要提供重复信息，不是独立证据。记录：`EVIDENCE_REDUNDANCY_OBSERVED`。最终 R2a Evaluation 必须区分 source-level repetition、chunk overlap duplication、chunker redundancy 与 future retrieval redundancy。

---

## Review Question 04

QUESTION_ID: Q04_CHINA_SUPPLY_CHAIN_EVIDENCE

QUESTION: 是否存在中国供应链或进口来源证据？
BUSINESS_INTENT: 检查 China/Vietnam sourcing 事实是否与必要公司上下文保持在可引用边界内。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/about-page

### Candidate Chunk A

- `chunk_id`: `4ec0891b-2262-5b87-9683-46302ebc0232`
- `heading`: `About Acme`
- `token_count`: `33`
- `offset`: `[0, 189)`
- `content`:

```text
# About Acme
Acme was founded in 1998 and operates distribution centers in California and Texas.

## Supply Network
The company sources steel components from factories in China and Vietnam.
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_HEADING_CONTEXT（有效标题/上下文）
LEO_NOTES: 该 Chunk 虽然只有约 33 tokens，但语义完整。Supply Network 明确说明公司从中国和越南工厂采购钢制零部件，因此提供了直接的 China sourcing / supply-chain evidence。该 Chunk 保留了 About Acme → Supply Network 的标题结构，主语、采购行为、产品与来源国家均没有被错误切断。不应因为 token 数少于 50 就自动合并。记录：`VALID_SHORT_CHUNK_OBSERVED`。该案例用于验证 semantic completeness 应优先于 fixed token length。

ANSWERABLE_FROM_CHUNKS: [x] YES（证据足够完整回答）
MIN_CHUNKS_REQUIRED: 1
EVIDENCE_MISSING: NONE
LEO_NOTES: 单个 Chunk 已足以证明存在中国供应链来源。无需其他 Chunk 才能回答该问题。

---

## Review Question 05

QUESTION_ID: Q05_PRODUCT_OR_HS_TARGET_MATCH

QUESTION: 哪些产品或 HS 信息支持目标匹配？
BUSINESS_INTENT: 判断产品类别是否足够支持 target match，并明确页面是否缺少 HS evidence。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/product-page

### Candidate Chunk A

- `chunk_id`: `8abf37e9-47b1-5864-8b49-e6e1e7e92d1e`
- `heading`: `Products`
- `token_count`: `18`
- `offset`: `[0, 112)`
- `content`:

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

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_HEADING_CONTEXT（有效标题/上下文）
LEO_NOTES: 该 Chunk 虽然只有约 18 tokens，但完整保留 Products 标题层级和两个产品类别：Fasteners（Bolts、Screws、Washers）与 Material Handling（Pallet jacks、Industrial carts、Warehouse racks），因此对于产品匹配具有直接证据价值。但当前 Chunk 未提供 HS code / HS classification，所以可以回答产品部分，但不能完整回答产品 + HS 信息。记录：`VALID_SHORT_CHUNK_OBSERVED` 与 `RETRIEVAL_RELEVANCE != ANSWER_COMPLETENESS`。该 Chunk 应被 Retrieval 命中，但 Grounded Answer 应明确指出缺失 HS evidence；不得因 token_count=18 或缺少 HS code 将其自动判断为无关或自动合并。

ANSWERABLE_FROM_CHUNKS: [x] PARTIAL（只能部分回答）
MIN_CHUNKS_REQUIRED: 1
EVIDENCE_MISSING: HS code / HS classification
LEO_NOTES: 记录 `RETRIEVAL_RELEVANT_BUT_INCOMPLETE_EVIDENCE`。Retrieval relevance 与 answer completeness 必须分开评估。

---

## Review Question 06

QUESTION: 公司业务角色是什么？
BUSINESS_INTENT: 判断 sourcing、distribution 与客户类型是否形成一个可解释的 business-role unit。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/homepage

### Candidate Chunk A

- `chunk_id`: `abdf3398-2b90-5196-b517-9cad40c52ffe`
- `heading`: `Acme Industrial`
- `token_count`: `27`
- `offset`: `[0, 166)`
- `content`:

```text
# Acme Industrial
Global sourcing and distribution for industrial fasteners.

## Markets
We serve importers, distributors, and manufacturers across the United States.
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_HEADING_CONTEXT（有效标题/上下文）
LEO_NOTES: 该 Chunk 可以独立支持“公司业务角色是什么”。证据明确说明 Acme 为工业紧固件提供 global sourcing and distribution，且服务对象包括美国的 importers、distributors 和 manufacturers。注意 `We serve importers` 表示客户对象包括进口商，不能据此推断 Acme 本身就是 importer。记录：`CUSTOMER_ROLE != COMPANY_ROLE`、`RETRIEVAL_RELEVANCE != CLAIM_ENTAILMENT` 与 `VALID_SHORT_CHUNK_OBSERVED`。正确检索到 Chunk 仍不代表最终生成的 Claim 一定被 Evidence 支持。该 Chunk 约 27 tokens，但语义完整、边界完整且可独立引用，不得仅因 token 数较少而自动合并。

ANSWERABLE_FROM_CHUNKS: [x] YES（证据足够完整回答）
MIN_CHUNKS_REQUIRED: 1
EVIDENCE_MISSING: NONE
LEO_NOTES: 该 Chunk 足以回答公司从事 industrial fastener sourcing and distribution，并服务 importers、distributors 与 manufacturers；回答时必须保持 customer role 与 company role 的语义边界。

---

## Review Question 07

QUESTION: 是否存在明显非目标业务？
BUSINESS_INTENT: 判断只有地点、成立年份和团队规模的 chunk 是否足以支持业务相关性判断。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/very-short-sections

### Candidate Chunk A

- `chunk_id`: `1575b6d9-124b-5f92-85ac-6a86db0b5b97`
- `heading`: `Locations`
- `token_count`: `15`
- `offset`: `[0, 68)`
- `content`:

```text
# Locations
California.

## Founded
1998.

## Team
Eighty employees.
```

LEO_RELEVANT: [x] NOT_RELEVANT（不相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_HEADING_CONTEXT（有效标题/上下文）
LEO_NOTES: 该 Chunk 包含有效公司元数据：location、founded year 和 team size，但这些事实无法回答“是否存在明显非目标业务”。必须保留 `ABSENCE_OF_EVIDENCE != EVIDENCE_OF_ABSENCE` 与 `ENTITY_RELEVANCE != QUESTION_RELEVANCE`：属于同一家公司的事实，不意味着该事实与当前 Query 有判别价值；不得因为没有检索到非目标业务证据，就推断公司不存在非目标业务。

ANSWERABLE_FROM_CHUNKS: [x] NO（当前证据无法回答）
MIN_CHUNKS_REQUIRED: 0
EVIDENCE_MISSING: 缺少能够判断目标/非目标业务的主营业务、产品、服务或行业分类证据。
LEO_NOTES: 当前 evaluation 文件使用整数型最小 Chunk 数，因此按 Human Ground Truth 记录为 `0`；未修改 database schema。

---

## Review Question 08

QUESTION: 公司页面里的关键产品或履约能力事实是什么？
BUSINESS_INTENT: 检查 heading/list structure 是否让 warehousing 与 distribution facts 保持可读。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/heading-list

### Candidate Chunk A

- `chunk_id`: `087d4224-4b0e-5aa2-8112-5559e2223b25`
- `heading`: `Capabilities`
- `token_count`: `23`
- `offset`: `[0, 139)`
- `content`:

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

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_HEADING_CONTEXT（有效标题/上下文）
LEO_NOTES: 该 Chunk 使用完整的 `Capabilities → Warehousing → Distribution` 标题层级，并明确给出 Cross-docking、Inventory storage、Pick and pack、Retail replenishment 和 Dealer delivery。这些信息足以独立回答当前 Query 中的“履约能力事实”。问题语义为“关键产品 或 履约能力事实”，因此无需同时存在产品证据。记录：`SHORT_CHUNK != BAD_CHUNK`。Chunk 质量应依据 semantic completeness、heading/context preservation、evidence independence 与 question answerability，而不能仅根据 token_count 判断；结构完整的短列表允许作为独立 Retrieval Unit。

ANSWERABLE_FROM_CHUNKS: [x] YES（证据足够完整回答）
MIN_CHUNKS_REQUIRED: 1
EVIDENCE_MISSING: NONE
LEO_NOTES: 当前 Chunk 的 `token_count=23`，符合项目 `<50` short-chunk review threshold，因此采用 `VALID_HEADING_CONTEXT`；未改变 threshold。

---

## Review Question 09

QUESTION: 是否有支持 Opportunity 判断的事实？
BUSINESS_INTENT: 判断设施、港口接收能力和 inland transit facts 是否构成可审计的 Opportunity 输入。

COMPANY: Acme Industrial
SOURCE_URL: https://fixture.example/blog-news

### Candidate Chunk A

- `chunk_id`: `f480fed7-390b-5782-ad26-8813b27bd6c2`
- `heading`: `Acme Opens Texas Distribution Center`
- `token_count`: `32`
- `offset`: `[0, 200)`
- `content`:

```text
# Acme Opens Texas Distribution Center
The new facility adds receiving capacity near major Gulf ports.

## Operations Update
Acme expects shorter inland transit times for imported industrial products.
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_HEADING_CONTEXT（有效标题/上下文）
LEO_NOTES: 当前 Chunk 明确提供 Company Facts：新建 Texas distribution center、增强 Gulf ports 附近 receiving capacity，以及预计缩短 imported industrial products 的 inland transit time。这些事实足够回答“是否存在支持 Opportunity 判断的事实？”，但不等于 Opportunity Judgment。必须保持 `COMPANY_FACT != OPPORTUNITY_JUDGMENT`：RAG / Evidence Layer 负责 Document → Chunk → Retrieval → Grounded Facts；Opportunity / Decision Layer 负责 Grounded Facts → Business Rules / Scoring / Reasoning → Opportunity Tier / Score / Decision。当前 evidence 不能直接证明成交概率、Opportunity score、客户价值、利润、当前货代关系或最终开发优先级。

ANSWERABLE_FROM_CHUNKS: [x] YES（证据足够完整回答）
MIN_CHUNKS_REQUIRED: 1
EVIDENCE_MISSING: NONE
LEO_NOTES: 当前 Chunk 的 `token_count=32`，符合项目 `<50` short-chunk review threshold，因此采用 `VALID_HEADING_CONTEXT`；未改变 Chunker 参数。

---

## Review Question 10

QUESTION: Freight-mode claim 的最佳 citation 应该是哪一个 chunk？
BUSINESS_INTENT: 在 PDF page chunks 中选择最直接、最小且足够的 citation target。

COMPANY: Pacific Components
SOURCE_URL: https://fixture.example/text-pdf-pages

### Candidate Chunk A

- `chunk_id`: `040d7eb2-187c-5585-b660-3e6d029d290c`
- `heading`: `Supplier Overview`
- `token_count`: `11`
- `offset`: `[11, 85)`
- `content`:

```text
# Supplier Overview
Pacific Components sources precision parts from Japan.
```

LEO_RELEVANT: [x] NOT_RELEVANT（不相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_ATOMIC_FACT（有效的独立事实）
CLAIM_ENTAILMENT: [x] NOT_ENTAILED
CITATION_SUFFICIENCY: [x] INSUFFICIENT
LEO_NOTES: Candidate A 是有效的 Japan sourcing 独立事实，但不能支持 freight-mode Claim。记录：`CHUNK_QUALITY != QUERY_RELEVANCE`、`QUERY_RELEVANCE != CLAIM_ENTAILMENT` 与 `CLAIM_ENTAILMENT != CITATION_SUFFICIENCY`。

### Candidate Chunk B

- `chunk_id`: `12628577-8370-53be-b73c-5d731531c7ef`
- `heading`: `Logistics`
- `token_count`: `17`
- `offset`: `[98, 201)`
- `content`:

```text
# Logistics
The company uses ocean freight for regular replenishment and air freight for urgent orders.
```

LEO_RELEVANT: [x] RELEVANT（直接相关）
LEO_BOUNDARY_PROBLEM: [x] GOOD（分块合理）
LEO_SHORT_CHUNK_CLASS: [x] VALID_ATOMIC_FACT（有效的独立事实）
CLAIM_ENTAILMENT: [x] ENTAILED
CITATION_SUFFICIENCY: [x] SUFFICIENT
LEO_NOTES: Candidate B 直接、完整支持 ocean freight 用于常规补货、air freight 用于紧急订单，是当前 Claim 的 minimal sufficient evidence。

ANSWERABLE_FROM_CHUNKS: [x] YES（证据足够完整回答）
MIN_CHUNKS_REQUIRED: 1
EVIDENCE_MISSING: NONE
BEST_CITATION: Candidate B (`12628577-8370-53be-b73c-5d731531c7ef`)
LEO_NOTES: `BEST_CITATION = MINIMAL_SUFFICIENT_EVIDENCE`。两个 Candidate 均低于项目 `<50` short-chunk review threshold，因此采用 `VALID_ATOMIC_FACT`；未修改 threshold 或 Chunker 参数。

---

## SHORT_CHUNK_REVIEW

### Distribution

| Token bucket | Chunk count |
|---|---:|
| `<20` | `6` |
| `20–49` | `4` |
| `50–99` | `0` |
| `>=100` | `9` |

对下面每个 `<50` token chunk，只做人工分类。Codex 不认定它正确、错误、碎片或 boilerplate。

### Short Chunk 01

- `chunk_id`: `abdf3398-2b90-5196-b517-9cad40c52ffe`
- `document`: `homepage`
- `heading`: `Acme Industrial`
- `token_count`: `27`
- `content`: `# Acme Industrial ↵ Global sourcing and distribution for industrial fasteners. ↵ ↵ ## Markets ↵ We serve importers, distributors, and manufacturers across the United States.`
- `previous_chunk_summary`: `NONE — first and only chunk in document`
- `next_chunk_summary`: `NONE — first and only chunk in document`

LEO_SHORT_CHUNK_JUDGMENT: [x] VALID_ATOMIC_FACT（有效的独立事实） [ ] VALID_HEADING_CONTEXT [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES: 完整且可独立理解的公司产品事实；能够直接支持主营产品类别判断。

### Short Chunk 02

- `chunk_id`: `4ec0891b-2262-5b87-9683-46302ebc0232`
- `document`: `about-page`
- `heading`: `About Acme`
- `token_count`: `33`
- `content`: `# About Acme ↵ Acme was founded in 1998 and operates distribution centers in California and Texas. ↵ ↵ ## Supply Network ↵ The company sources steel components from factories in China and Vietnam.`
- `previous_chunk_summary`: `NONE — first and only chunk in document`
- `next_chunk_summary`: `NONE — first and only chunk in document`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [ ] VALID_HEADING_CONTEXT [ ] FRAGMENTED [ ] BOILERPLATE [x] SHOULD_MERGE_WITH_PREVIOUS（建议与上一 Chunk 合并） [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES: 产品事实相关，但 5-token chunk 过短，且与前一 Company Overview 属于同一产品语义单元。

### Short Chunk 03

- `chunk_id`: `8abf37e9-47b1-5864-8b49-e6e1e7e92d1e`
- `document`: `product-page`
- `heading`: `Products`
- `token_count`: `18`
- `content`: `# Products ↵ ## Fasteners ↵ Bolts ↵ Screws ↵ Washers ↵ ↵ ## Material Handling ↵ Pallet jacks ↵ Industrial carts ↵ Warehouse racks`
- `previous_chunk_summary`: `NONE — first and only chunk in document`
- `next_chunk_summary`: `NONE — first and only chunk in document`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [x] VALID_HEADING_CONTEXT（有效标题/上下文） [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES: 33 tokens 但语义完整，保留 About Acme → Supply Network 标题结构和完整 China sourcing 事实；记录 `VALID_SHORT_CHUNK_OBSERVED`。

### Short Chunk 04

- `chunk_id`: `f480fed7-390b-5782-ad26-8813b27bd6c2`
- `document`: `blog-news`
- `heading`: `Acme Opens Texas Distribution Center`
- `token_count`: `32`
- `content`: `# Acme Opens Texas Distribution Center ↵ The new facility adds receiving capacity near major Gulf ports. ↵ ↵ ## Operations Update ↵ Acme expects shorter inland transit times for imported industrial products.`
- `previous_chunk_summary`: `NONE — first and only chunk in document`
- `next_chunk_summary`: `NONE — first and only chunk in document`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [x] VALID_HEADING_CONTEXT（有效标题/上下文） [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES: 18 tokens 但完整保留 Products、Fasteners、Material Handling 标题层级与产品列表；记录 `VALID_SHORT_CHUNK_OBSERVED`。

### Short Chunk 05

- `chunk_id`: `087d4224-4b0e-5aa2-8112-5559e2223b25`
- `document`: `heading-list`
- `heading`: `Capabilities`
- `token_count`: `23`
- `content`: `# Capabilities ↵ ## Warehousing ↵ - Cross-docking ↵ - Inventory storage ↵ - Pick and pack ↵ ↵ ## Distribution ↵ - Retail replenishment ↵ - Dealer delivery`
- `previous_chunk_summary`: `NONE — first and only chunk in document`
- `next_chunk_summary`: `NONE — first and only chunk in document`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [ ] VALID_HEADING_CONTEXT [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES:

### Short Chunk 06

- `chunk_id`: `1575b6d9-124b-5f92-85ac-6a86db0b5b97`
- `document`: `very-short-sections`
- `heading`: `Locations`
- `token_count`: `15`
- `content`: `# Locations ↵ California. ↵ ↵ ## Founded ↵ 1998. ↵ ↵ ## Team ↵ Eighty employees.`
- `previous_chunk_summary`: `NONE — first and only chunk in document`
- `next_chunk_summary`: `NONE — first and only chunk in document`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [ ] VALID_HEADING_CONTEXT [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES:

### Short Chunk 07

- `chunk_id`: `2daad9a3-5b68-5e72-a0b4-70e623cad4c4`
- `document`: `repeated-footer-nav`
- `heading`: `Company Overview`
- `token_count`: `11`
- `content`: `# Company Overview ↵ Acme imports industrial fasteners for regional distribution.`
- `previous_chunk_summary`: `NONE — first chunk in document`
- `next_chunk_summary`: `Product card: stainless bolts.`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [ ] VALID_HEADING_CONTEXT [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES:

### Short Chunk 08

- `chunk_id`: `d26f680f-dbe5-5247-843f-4c7788358d85`
- `document`: `repeated-footer-nav`
- `heading`: `Company Overview > Product card: stainless bolts`
- `token_count`: `5`
- `content`: `Product card: stainless bolts`
- `previous_chunk_summary`: `Company overview says Acme imports industrial fasteners for regional distribution.`
- `next_chunk_summary`: `NONE — last chunk in document`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [ ] VALID_HEADING_CONTEXT [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES:

### Short Chunk 09

- `chunk_id`: `040d7eb2-187c-5585-b660-3e6d029d290c`
- `document`: `text-pdf-pages`
- `heading`: `Supplier Overview`
- `token_count`: `11`
- `content`: `# Supplier Overview ↵ Pacific Components sources precision parts from Japan.`
- `previous_chunk_summary`: `NONE — first chunk in document`
- `next_chunk_summary`: `Page 2 Logistics says ocean freight is used regularly and air freight for urgent orders.`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [ ] VALID_HEADING_CONTEXT [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES:

### Short Chunk 10

- `chunk_id`: `12628577-8370-53be-b73c-5d731531c7ef`
- `document`: `text-pdf-pages`
- `heading`: `Logistics`
- `token_count`: `17`
- `content`: `# Logistics ↵ The company uses ocean freight for regular replenishment and air freight for urgent orders.`
- `previous_chunk_summary`: `Page 1 Supplier Overview says Pacific Components sources precision parts from Japan.`
- `next_chunk_summary`: `NONE — last chunk in document`

LEO_SHORT_CHUNK_JUDGMENT: [ ] VALID_ATOMIC_FACT [ ] VALID_HEADING_CONTEXT [ ] FRAGMENTED [ ] BOILERPLATE [ ] SHOULD_MERGE_WITH_PREVIOUS [ ] SHOULD_MERGE_WITH_NEXT
LEO_SHORT_CHUNK_NOTES:

## Completion

- [ ] 19 candidate-level `LEO_RELEVANT` boxes reviewed.
- [ ] 19 candidate-level `LEO_BOUNDARY_PROBLEM` boxes reviewed.
- [ ] 10 `MIN_CHUNKS_REQUIRED` values completed.
- [ ] 10 question-level `LEO_NOTES` reviewed.
- [ ] 10 `<50` token chunks classified in `SHORT_CHUNK_REVIEW`.
