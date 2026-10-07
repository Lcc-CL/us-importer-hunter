# L03 — Leo 中文逐题人工评测交接

日期：2026-08-10
状态：**R2A FINAL EVALUATION AND BASELINE**

## 使用规则

- 面向 Leo 的问题、解释、操作说明和标签说明全部使用中文。
- 数据库枚举值、字段名、类名和 fixture 原始英文保持不变。
- Q1–Q10 Human Ground Truth 已全部完成，不再生成 Q11 或继续逐题评测。
- Q10 已由 Leo 明确接受并保存，不再包含未确认建议。
- UUID、offset、hash、tokenizer 与内部 metadata 默认折叠。

## 人工评测进度

- 已完成：`10 / 10`
- 剩余：`0 / 10`
- 下一步：生成 `R2A_FINAL_HUMAN_EVALUATION_REPORT`

## 最终 Human Metrics — Baseline 10/10

- `question_evidence_coverage`（YES 或 PARTIAL）：`90.00%`（`9/10`）
- `complete_answer_rate`（YES）：`70.00%`（`7/10`）
- `partial_answer_rate`（PARTIAL）：`20.00%`（`2/10`）
- `no_answer_rate`（NO）：`10.00%`（`1/10`）
- `average_minimum_chunks_required`：`1.11`（仅统计 `9` 个 YES/PARTIAL；Q7 的 `NO` 存储值为 `0`）
- `boundary_break_count`：`1`
- `short_chunk_merge_candidates`：`1`
- `valid_short_chunk_count`：`9`
- retrieval relevance distribution：`RELEVANT=13`、`PARTIALLY_RELEVANT=4`、`NOT_RELEVANT=2`
- answerability distribution：`YES=7`、`PARTIAL=2`、`NO=1`
- claim entailment distribution：`ENTAILED=1`、`NOT_ENTAILED=1`、`NOT_EVALUATED=17`
- citation sufficiency distribution：`SUFFICIENT=1`、`INSUFFICIENT=1`、`NOT_EVALUATED=17`
- 已标注 candidate chunks：`19 / 19`

本轮 10 个 fixtures 仅建立 `RAG_CHUNKING_BASELINE_V1`，不得声称已经证明 production optimal。

## 当前工程发现

- `SHORT_CHUNK_MERGE_CANDIDATE`：Q1 Candidate B。
- `VALID_SHORT_CHUNK_OBSERVED`：Q1 Candidate A、Q4 Candidate A、Q5 Candidate A。
- `RETRIEVAL_REDUNDANCY_CANDIDATE`：Q2 高度重复 candidates。
- `EVIDENCE_REDUNDANCY_OBSERVED`：Q3 必须区分 source repetition、overlap、chunker attribution 与 future retrieval。
- `RETRIEVAL_RELEVANT_BUT_INCOMPLETE_EVIDENCE`：Q5 应被检索，但回答必须声明缺少 HS evidence。
- `CUSTOMER_ROLE != COMPANY_ROLE`：Q6 的 “serve importers” 描述客户群，不能推断 Acme 本身是 importer。
- `RETRIEVAL_RELEVANCE != CLAIM_ENTAILMENT`：Q6 证明正确命中证据不等于任意生成 Claim 都被该证据支持。
- `ABSENCE_OF_EVIDENCE != EVIDENCE_OF_ABSENCE`：Q7 未发现非目标业务证据，不能推出不存在非目标业务。
- `ENTITY_RELEVANCE != QUESTION_RELEVANCE`：Q7 公司元数据属于正确实体，但对当前业务判别问题不相关。
- `SHORT_CHUNK != BAD_CHUNK`：Q8 的 23-token 结构化能力列表语义完整，可作为独立 Retrieval Unit。
- `COMPANY_FACT != OPPORTUNITY_JUDGMENT`：Q9 的设施与运输事实是 Opportunity 输入，不是评分或决策。
- `CHUNK_QUALITY != QUERY_RELEVANCE`：Q10 Candidate A 是好 Chunk，但与 freight-mode Query 不相关。
- `QUERY_RELEVANCE != CLAIM_ENTAILMENT`：相关性与 Claim 是否被逻辑支持必须分开标注。
- `CLAIM_ENTAILMENT != CITATION_SUFFICIENCY`：即使存在 entailment，也必须检查单个引用是否足够。
- `BEST_CITATION = MINIMAL_SUFFICIENT_EVIDENCE`：Q10 Candidate B 是最小且足够的 citation target。

---

## 已完成记录：Q1

问题：公司主营产品是什么？
问题 ID：`Q01_MAIN_PRODUCTS`

### 候选 Chunk A

CHUNK_ID：`2daad9a3-5b68-5e72-a0b4-70e623cad4c4`
Token 数：`11`
标题：`Company Overview`
边界类型：`HEADING_SECTION; FILTERED_SOURCE_GAP_AFTER; OVERLAP=0; HARD_SPLIT=NO`

原始内容：

```text
# Company Overview
Acme imports industrial fasteners for regional distribution.
```

前一段上下文：

```text
无：文档起点
```

后一段上下文：

```text
Product card: stainless bolts
```

相关性：
[x] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[ ] NOT_APPLICABLE — 不适用
[x] VALID_ATOMIC_FACT — 有效的独立事实
[ ] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

完整且可独立理解的公司产品事实。
明确说明 Acme 进口 industrial fasteners，
能够直接支持主营产品类别判断。

### 候选 Chunk B

CHUNK_ID：`d26f680f-dbe5-5247-843f-4c7788358d85`
Token 数：`5`
标题：`Company Overview > Product card: stainless bolts`
边界类型：`FILTERED_SOURCE_GAP_BEFORE; DOCUMENT_END; OVERLAP=0; HARD_SPLIT=NO`

原始内容：

```text
Product card: stainless bolts
```

前一段上下文：

```text
# Company Overview
Acme imports industrial fasteners for regional distribution.
```

后一段上下文：

```text
无：文档终点
```

相关性：
[x] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[ ] GOOD — 分块合理
[x] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[ ] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[ ] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[x] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

产品事实本身相关，但 5-token chunk 过短，
且与前一 Company Overview 属于同一产品语义单元。
建议与 previous chunk 合并。

问题级判断：
[x] YES — 证据足够完整回答
[ ] PARTIAL — 只能部分回答
[ ] NO — 当前证据无法回答

最少需要 Chunk 数：`2`
缺失证据：`NONE`

---

## 已完成记录：Q2

问题：公司是否与 fitness equipment 相关？
问题 ID：`Q02_FITNESS_RELEVANCE`

### 候选 Chunk A

CHUNK_ID：`0d5af75e-23ba-518b-944a-e90ae81b7c7b`
Token 数：`507`
标题：`Industrial Catalog`
边界类型：`DOCUMENT_START; SENTENCE_BOUNDARY_AFTER; OVERLAP_AFTER; HARD_SPLIT=NO`

原始内容：

```text
# Industrial Catalog
The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers.
```

前一段上下文：

```text
无：文档起点
```

后一段上下文：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
```

相关性：
[ ] RELEVANT — 直接相关
[x] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[x] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[ ] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

该分块提供建筑/制造业工业零部件业务信号，
对判断公司是否属于 fitness equipment 行业有帮助，
但不能单独证明公司完全不涉及健身器材。

### 候选 Chunk B

CHUNK_ID：`a9546ade-0385-5876-9d40-c317f775fa4c`
Token 数：`504`
标题：`Industrial Catalog`
边界类型：`SENTENCE_BOUNDARY_BEFORE_AND_AFTER; OVERLAP_BEFORE_AND_AFTER; HARD_SPLIT=NO`

原始内容：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers.
```

前一段上下文：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
```

后一段上下文：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
```

相关性：
[ ] RELEVANT — 直接相关
[x] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[x] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[ ] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

与 Candidate A 基本属于相同业务证据。
具有部分相关性，但没有提供 fitness equipment 的明确正向或排除证据。

### 候选 Chunk C

CHUNK_ID：`3cbbc09d-4c88-541e-aeb2-fe670a4f5ee0`
Token 数：`504`
标题：`Industrial Catalog`
边界类型：`SENTENCE_BOUNDARY_BEFORE_AND_AFTER; OVERLAP_BEFORE_AND_AFTER; HARD_SPLIT=NO`

原始内容：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers.
```

前一段上下文：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
```

后一段上下文：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
```

相关性：
[ ] RELEVANT — 直接相关
[x] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[x] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[ ] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

提供建筑/制造工业组件信号，但与其他候选高度重复。
没有增加足以确认或完全排除 fitness equipment 的独立证据。

### 候选 Chunk D

CHUNK_ID：`87f8d4d7-7089-5724-8389-91656c1f384b`
Token 数：`504`
标题：`Industrial Catalog`
边界类型：`SENTENCE_BOUNDARY_BEFORE; DOCUMENT_END; OVERLAP_BEFORE; HARD_SPLIT=NO`

原始内容：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers. The catalog lists corrosion resistant components for construction and manufacturing customers.
```

前一段上下文：

```text
The catalog lists corrosion resistant components for construction and manufacturing customers.
```

后一段上下文：

```text
无：文档终点
```

相关性：
[ ] RELEVANT — 直接相关
[x] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[x] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[ ] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

具有弱负向业务相关性证据，但与 A/B/C 高度重复，
单独无法证明公司完全不涉及 fitness equipment。

问题级判断：
[ ] YES — 证据足够完整回答
[x] PARTIAL — 只能部分回答
[ ] NO — 当前证据无法回答

最少需要 Chunk 数：`1`
缺失证据：缺少明确产品分类、完整产品目录或业务描述。

---

## 已完成记录：Q3

问题：是否存在 importer / distributor / retailer 证据？
问题 ID：`Q03_IMPORT_DISTRIBUTION_EVIDENCE`

### 高度重复候选组

逐 Chunk Ground Truth 写回对象：

- `c00b7385-45db-5b35-9ba3-ec5d65a199f0`（507 tokens）
- `6b783be7-0503-5a4d-b773-9609d0b75d7b`（504 tokens）
- `05be6072-e616-5649-9d29-55144ec3d49b`（504 tokens）
- `29e63226-a7db-50f2-a951-99e1cf4beb28`（504 tokens）
- `e08a2235-2487-591d-ba93-f2f9c5af9f17`（224 tokens）

相关性：
[x] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[x] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[ ] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

原文明确说明 Acme 每月协调来自亚洲供应商的集装箱进口，
并通过多个美国港口进入美国。

这属于直接 importer / import operations 行为证据。

虽然当前证据没有证明 distributor 或 retailer 身份，
但问题采用 importer / distributor / retailer 的 OR 语义，
因此 importer 证据已经足以回答当前问题。

多个 Candidate Chunk 高度重复，
不得把重复 Chunk 当成多个独立证据。

问题级判断：
[x] YES — 证据足够完整回答
[ ] PARTIAL — 只能部分回答
[ ] NO — 当前证据无法回答

最少需要 Chunk 数：`1`
缺失证据：`NONE`

---

## 已完成记录：Q4

问题：是否存在中国供应链或进口来源证据？
问题 ID：`Q04_CHINA_SUPPLY_CHAIN_EVIDENCE`

### 候选 Chunk A

CHUNK_ID：`4ec0891b-2262-5b87-9683-46302ebc0232`
Token 数：`33`
标题：`About Acme`
边界类型：`DOCUMENT_START_AND_END; STRUCTURE_AWARE_HEADING_MERGE; OVERLAP=0; HARD_SPLIT=NO`

原始内容：

```text
# About Acme
Acme was founded in 1998 and operates distribution centers in California and Texas.

## Supply Network
The company sources steel components from factories in China and Vietnam.
```

前一段上下文：

```text
无：文档起点
```

后一段上下文：

```text
无：文档终点
```

相关性：
[x] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[ ] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[x] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

该 Chunk 虽然只有约 33 tokens，但语义完整。

Supply Network 明确说明：
公司从中国和越南工厂采购钢制零部件。

因此它提供了直接的 China sourcing / supply-chain evidence。

该 Chunk 保留了 About Acme → Supply Network 的标题结构，
主语、采购行为、产品与来源国家均没有被错误切断。

不应因为 token 数少于 50 就自动合并。

记录：

VALID_SHORT_CHUNK_OBSERVED

该案例用于验证：
semantic completeness 应优先于 fixed token length。

问题级判断：
[x] YES — 证据足够完整回答
[ ] PARTIAL — 只能部分回答
[ ] NO — 当前证据无法回答

最少需要 Chunk 数：`1`
缺失证据：`NONE`

---

## 已完成记录：Q5

问题：哪些产品或 HS 信息支持目标匹配？
问题 ID：`Q05_PRODUCT_OR_HS_TARGET_MATCH`

### 候选 Chunk A

CHUNK_ID：`8abf37e9-47b1-5864-8b49-e6e1e7e92d1e`
Token 数：`18`
标题：`Products`
边界类型：`DOCUMENT_START_AND_END; STRUCTURE_AWARE_HEADING_MERGE; OVERLAP=0; HARD_SPLIT=NO`

原始内容：

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

前一段上下文：

```text
无：文档起点
```

后一段上下文：

```text
无：文档终点
```

相关性：
[x] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[ ] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[x] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

该 Chunk 虽然只有约 18 tokens，但完整保留 Products 标题层级和两个产品类别：

Fasteners:
- Bolts
- Screws
- Washers

Material Handling:
- Pallet jacks
- Industrial carts
- Warehouse racks

因此对于产品匹配具有直接证据价值。

但当前 Chunk 未提供 HS code / HS classification，
所以可以回答产品部分，但不能完整回答产品 + HS 信息。

记录：

VALID_SHORT_CHUNK_OBSERVED

同时记录核心 Evaluation 区别：

RETRIEVAL_RELEVANCE != ANSWER_COMPLETENESS

该 Chunk 应被 Retrieval 命中，
但 Grounded Answer 应明确指出缺失 HS evidence。

不得因为：
- token_count = 18
- 缺少 HS code

而将该 Chunk 自动判断为无关或自动合并。

问题级判断：
[ ] YES — 证据足够完整回答
[x] PARTIAL — 只能部分回答
[ ] NO — 当前证据无法回答

最少需要 Chunk 数：`1`
缺失证据：`HS code / HS classification`

Leo 问题备注：

该 Chunk 应被 Retrieval 命中，但 Grounded Answer 必须明确指出缺失 HS evidence。
记录：`RETRIEVAL_RELEVANT_BUT_INCOMPLETE_EVIDENCE`。

---

## 已完成记录：Q6

问题：公司业务角色是什么？
问题 ID：`Q06_COMPANY_BUSINESS_ROLE`

### 候选 Chunk A

CHUNK_ID：`abdf3398-2b90-5196-b517-9cad40c52ffe`
Token 数：`27`
标题：`Acme Industrial`
边界类型：`DOCUMENT_START_AND_END; STRUCTURE_AWARE_HEADING_MERGE; OVERLAP=0; HARD_SPLIT=NO`

原始内容：

```text
# Acme Industrial
Global sourcing and distribution for industrial fasteners.

## Markets
We serve importers, distributors, and manufacturers across the United States.
```

相关性：
[x] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[ ] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[x] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

该 Chunk 可以独立支持“公司业务角色是什么”。证据明确说明 Acme 为工业紧固件提供
global sourcing and distribution，且服务对象包括美国的 importers、distributors 和 manufacturers。

`We serve importers` 表示客户对象包括进口商，不能据此推断 Acme 本身就是 importer。记录：
`CUSTOMER_ROLE != COMPANY_ROLE` 与 `RETRIEVAL_RELEVANCE != CLAIM_ENTAILMENT`。正确检索到 Chunk
仍不代表最终生成的 Claim 一定被 Evidence 支持。

该 Chunk 约 27 tokens，但语义完整、边界完整且可独立引用，不得仅因 token 数较少而自动合并。
记录：`VALID_SHORT_CHUNK_OBSERVED`。

问题级判断：
[x] YES — 证据足够完整回答
[ ] PARTIAL — 只能部分回答
[ ] NO — 当前证据无法回答

最少需要 Chunk 数：`1`
缺失证据：`NONE`

Leo 问题备注：回答必须保持 customer role 与 company role 的语义边界。

---

## 已完成记录：Q7

问题：是否存在明显非目标业务？
问题 ID：`Q07_NON_TARGET_BUSINESS`

### 候选 Chunk A

CHUNK_ID：`1575b6d9-124b-5f92-85ac-6a86db0b5b97`
Token 数：`15`
标题：`Locations`
边界类型：`DOCUMENT_START_AND_END; STRUCTURE_AWARE_HEADING_MERGE; OVERLAP=0; HARD_SPLIT=NO`

原始内容：

```text
# Locations
California.

## Founded
1998.

## Team
Eighty employees.
```

相关性：
[ ] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[x] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[ ] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[x] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

该 Chunk 包含有效公司元数据：location、founded year 和 team size，但这些事实无法回答
“是否存在明显非目标业务”。必须保留：

- `ABSENCE_OF_EVIDENCE != EVIDENCE_OF_ABSENCE`
- `ENTITY_RELEVANCE != QUESTION_RELEVANCE`

属于同一家公司的事实，不意味着该事实与当前 Query 有判别价值。不得因为没有检索到非目标业务
证据，就推断公司“不存在非目标业务”。

问题级判断：
[ ] YES — 证据足够完整回答
[ ] PARTIAL — 只能部分回答
[x] NO — 当前证据无法回答

最少需要 Chunk 数：`0`
缺失证据：缺少能够判断目标/非目标业务的主营业务、产品、服务或行业分类证据。

Leo 问题备注：当前 evaluation 文件使用整数型最小 Chunk 数，因此记录为 `0`；未修改 database schema。

---

## 已完成记录：Q8

问题：公司页面里的关键产品或履约能力事实是什么？
问题 ID：`Q08_PAGE_PRODUCT_OR_FULFILLMENT_FACTS`

### 候选 Chunk A

CHUNK_ID：`087d4224-4b0e-5aa2-8112-5559e2223b25`
Token 数：`23`
标题：`Capabilities`
边界类型：`DOCUMENT_START_AND_END; STRUCTURE_AWARE_HEADING_MERGE; OVERLAP=0; HARD_SPLIT=NO`

原始内容：

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

相关性：
[x] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[ ] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[x] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

该 Chunk 使用完整的 `Capabilities → Warehousing → Distribution` 标题层级，并明确给出
Cross-docking、Inventory storage、Pick and pack、Retail replenishment 和 Dealer delivery。
这些信息足以独立回答当前 Query 中的“履约能力事实”。

问题语义为“关键产品 或 履约能力事实”，因此无需同时存在产品证据。当前履约能力 evidence
已经足够完整回答该问题。

记录：`SHORT_CHUNK != BAD_CHUNK`。Chunk 质量应依据 semantic completeness、
heading/context preservation、evidence independence 与 question answerability，而不能仅根据
token_count 判断。结构完整的短列表允许作为独立 Retrieval Unit。

问题级判断：
[x] YES — 证据足够完整回答
[ ] PARTIAL — 只能部分回答
[ ] NO — 当前证据无法回答

最少需要 Chunk 数：`1`
缺失证据：`NONE`

Leo 问题备注：`token_count=23`，符合项目 `<50` short-chunk review threshold，因此采用
`VALID_HEADING_CONTEXT`；未改变 threshold。

---

## 已完成记录：Q9

问题：是否有支持 Opportunity 判断的事实？
问题 ID：`Q09_OPPORTUNITY_SUPPORTING_FACTS`

### 候选 Chunk A

CHUNK_ID：`f480fed7-390b-5782-ad26-8813b27bd6c2`
Token 数：`32`
标题：`Acme Opens Texas Distribution Center`
边界类型：`DOCUMENT_START_AND_END; STRUCTURE_AWARE_HEADING_MERGE; OVERLAP=0; HARD_SPLIT=NO`

原始内容：

```text
# Acme Opens Texas Distribution Center
The new facility adds receiving capacity near major Gulf ports.

## Operations Update
Acme expects shorter inland transit times for imported industrial products.
```

相关性：
[x] RELEVANT — 直接相关
[ ] PARTIALLY_RELEVANT — 部分相关 / 证据不完整
[ ] NOT_RELEVANT — 不相关

边界：
[x] GOOD — 分块合理
[ ] BROKEN_BEFORE — 前文被错误截断
[ ] BROKEN_AFTER — 后文被错误截断
[ ] BROKEN_BOTH — 前后均被错误截断

短 Chunk 分类：
[ ] NOT_APPLICABLE — 不适用
[ ] VALID_ATOMIC_FACT — 有效的独立事实
[x] VALID_HEADING_CONTEXT — 有效标题/上下文
[ ] FRAGMENTED — 碎片化
[ ] BOILERPLATE — 模板/无效重复内容
[ ] SHOULD_MERGE_PREVIOUS — 建议与上一 Chunk 合并
[ ] SHOULD_MERGE_NEXT — 建议与下一 Chunk 合并

Leo 备注：

当前 Chunk 明确提供 Company Facts：新建 Texas distribution center、增强 Gulf ports 附近
receiving capacity，以及预计缩短 imported industrial products 的 inland transit time。这些事实
足够回答“是否存在支持 Opportunity 判断的事实？”，但不等于 Opportunity Judgment。

必须保持 `COMPANY_FACT != OPPORTUNITY_JUDGMENT`：RAG / Evidence Layer 负责 Document → Chunk →
Retrieval → Grounded Facts；Opportunity / Decision Layer 负责 Grounded Facts → Business Rules /
Scoring / Reasoning → Opportunity Tier / Score / Decision。

当前 evidence 不能直接证明成交概率、Opportunity score、客户价值、利润、当前货代关系或最终
开发优先级，因此禁止把这些内容作为当前 Chunk 的 Ground Truth。

问题级判断：
[x] YES — 证据足够完整回答
[ ] PARTIAL — 只能部分回答
[ ] NO — 当前证据无法回答

最少需要 Chunk 数：`1`
缺失证据：`NONE`

Leo 问题备注：`token_count=32`，符合项目 `<50` short-chunk review threshold，因此采用
`VALID_HEADING_CONTEXT`；未改变 Chunker 参数。

---

## 已完成记录：Q10

问题：Freight-mode claim 的最佳 citation 应该是哪一个 chunk？
问题 ID：`Q10_BEST_CITATION_FOR_FREIGHT_MODE_CLAIM`

待验证 Claim：Pacific Components 使用 ocean freight 进行常规补货，并使用 air freight 处理紧急订单。

### Candidate A

- Chunk ID：`040d7eb2-187c-5585-b660-3e6d029d290c`
- Token 数：`11`
- PDF Page：`1`
- 内容：`Pacific Components sources precision parts from Japan.`
- relevance：`NOT_RELEVANT`
- boundary：`GOOD`
- short chunk class：`VALID_ATOMIC_FACT`
- claim entailment：`NOT_ENTAILED`
- citation sufficiency：`INSUFFICIENT`

Candidate A 是有效的 Japan sourcing 独立事实，但不能支持 freight-mode Claim。

### Candidate B

- Chunk ID：`12628577-8370-53be-b73c-5d731531c7ef`
- Token 数：`17`
- PDF Page：`2`
- 内容：`The company uses ocean freight for regular replenishment and air freight for urgent orders.`
- relevance：`RELEVANT`
- boundary：`GOOD`
- short chunk class：`VALID_ATOMIC_FACT`
- claim entailment：`ENTAILED`
- citation sufficiency：`SUFFICIENT`

Candidate B 直接、完整支持 freight-mode Claim，是 minimal sufficient evidence。

### 问题级 Ground Truth

- answerable：`YES`
- minimum chunks required：`1`
- evidence missing：`NONE`
- best citation：Candidate B，`12628577-8370-53be-b73c-5d731531c7ef`

### 最终工程原则

- `CHUNK_QUALITY != QUERY_RELEVANCE`
- `QUERY_RELEVANCE != CLAIM_ENTAILMENT`
- `CLAIM_ENTAILMENT != CITATION_SUFFICIENCY`
- `BEST_CITATION = MINIMAL_SUFFICIENT_EVIDENCE`

---

## STOP HUMAN QUESTION LOOP

Q1–Q10 Human Evaluation 到此结束。禁止生成 Q11。下一步进入
`R2A_FINAL_EVALUATION_AND_BASELINE`，先生成最终报告与基线，再决定 `KEEP_CURRENT_CHUNKER`
或 `TUNE_CHUNKER`。
