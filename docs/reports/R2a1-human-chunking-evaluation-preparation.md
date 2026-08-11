# R2a.1 — Human Chunking Evaluation Preparation

日期：2026-08-10
状态：**HUMAN REVIEW COMPLETE — SUPERSEDED BY FINAL REPORT**
分支：`feat/rag-r2a-deterministic-chunking`
PR：`#34`（保持 OPEN；本阶段不得 merge）

## 1. Objective

R2a.1 不继续增加 RAG 基础设施。目标是让 Leo 用 10 个真实业务问题判断
`ResearchDocumentChunk` 是否适合作为 US Importer Hunter Research 的 retrieval unit。

本阶段没有 Retriever，因此不使用 Recall@K、MRR、nDCG，也不调用 pgvector、embedding、LLM
或外部 paid provider。

## 2. Inputs

- R1 ingestion fixtures：`10` cases。
- R2a chunking evaluation fixtures：`10` documents。
- Existing human candidate template：`docs/learning/experiments/L03-chunking-relevance-template.jsonl`。
- Existing deterministic visualization：`apps/backend/scripts/visualize_research_chunks.py`。

R1 fixtures 用于覆盖 document eligibility、provenance、duplicate、quarantine、oversize 与 cleaned
structure 场景。R2a fixtures 产生本轮需要人工观察的 `19` 个稳定 chunks。

## 3. Prepared Artifacts

- `docs/learning/experiments/L03-chunking-human-review.md`
  - 10 个业务问题。
  - 覆盖 product、fitness relevance、import/distribution evidence、China sourcing、target match、
    company role、non-target evidence、page facts、Opportunity evidence 与 best citation。
  - 展示 company、document、source URL、candidate chunk ID/index/heading/token/offset/content。
  - Q1–Q10 Human Ground Truth 已保存。
- `docs/learning/experiments/L03-leo-review-handoff.md`
  - 面向 Leo 的中文逐题 Review 入口。
  - Human question loop 已结束；禁止生成 Q11。
  - enum 值保持英文，中文解释仅用于人类阅读层。
- `docs/learning/experiments/L03-chunk-boundary-review.md`
  - 展示 10 个 documents 的 `document → sections → chunks`。
  - 标记 section/page boundary、sentence-safe split、overlap region、hard split observation、
    boilerplate removal 与 duplicate removal。
- `docs/learning/notes/L03-chunking-notes.md`
  - 增加 10 个由 Leo 自己回答的 chunking 问题。

## 4. Current Chunker Configuration

| Setting | Value |
|---|---|
| chunker version | `structure-recursive-v1:e89d30e35ee3` |
| tokenizer profile | `unicode-lexical-v1` |
| target token range | target around `500` local profile tokens |
| hard max | `900` local profile tokens |
| overlap max | `80` local profile tokens, oversized sections only |

这里的 token 是 deterministic local lexical profile，不是 provider billing token。

## 5. Automatic Metrics

对全部 10 个 R2a fixtures 使用默认配置运行两次 deterministic plan：

| Metric | Result | Calibration target |
|---|---:|---:|
| documents | `10` | fixture coverage |
| chunks | `19` | observation only |
| source tokens | `3,981` | observation only |
| emitted tokens | `4,454` | observation only |
| `hard_limit_violation` | `0` | `0` |
| `offset_roundtrip_error` | `0` | `0` |
| `stable_identity_rate` | `100%` (`19/19`) | `100%` |
| aggregate raw `boilerplate_ratio` | `0.15%` | `< 10%` initial target |
| aggregate raw `duplicate_ratio` | `0.13%` | observation/minimize |
| aggregate raw `overlap_ratio` | `11.14%` | necessity not auto-judged |

Per-fixture stress observations：

- `long-paragraph`：5 chunks，raw overlap `12.48%`。
- `oversized-section`：4 chunks，raw overlap `10.70%`。
- `repeated-footer-nav`：removed duplicate ratio `18.52%`，removed boilerplate ratio `22.22%`；
  这是故意构造的 noisy fixture，aggregate ratio 仍单独记录。
- 未观察到 token-boundary hard split；两个 oversized fixtures 均在完整 sentence boundary 切分。

## 6. Human-Dependent Metrics

当前完成 `10 / 10` 问题、`19 / 19` candidate chunks。最终决策与完整分析见
`docs/reports/R2a-final-human-evaluation-report.md`：

| Metric | Provisional result | Initial calibration target |
|---|---:|---:|
| `question_evidence_coverage`（YES 或 PARTIAL） | `90.00%` (`9/10`) | `>= 90%` |
| `complete_answer_rate`（仅 YES） | `70.00%` (`7/10`) | observation only |
| `partial_answer_rate`（仅 PARTIAL） | `20.00%` (`2/10`) | observation only |
| `no_answer_rate`（仅 NO） | `10.00%` (`1/10`) | observation only |
| `boundary_break_count` | `1` | `0` obvious breaks |
| `average_minimum_chunks_required` | `1.11`（仅 9 个 YES/PARTIAL；Q7 存储值=`0`） | usually `1–3` when answerable |
| `short_chunk_merge_candidates` | `1` | observation only |
| `valid_short_chunk_count` | `9` | observation only |
| retrieval relevance distribution | `RELEVANT=13`, `PARTIALLY_RELEVANT=4`, `NOT_RELEVANT=2` | observation only |
| answerability distribution | `YES=7`, `PARTIAL=2`, `NO=1` | observation only |
| unnecessary overlap ratio | `PENDING_HUMAN_LABEL` | `< 15%` |

Review flags：

- 需要大量碎片才能理解：`CHUNK_TOO_SMALL_OR_FRAGMENTED`。
- 单个 chunk 混合过多独立主题：`CHUNK_TOO_LARGE_OR_MIXED`。

Q1–Q10 均仅记录 Leo 明确确认的 Human Ground Truth。Q10 额外记录 claim entailment、citation
sufficiency 与 best citation；Q1–Q9 不追溯推断这些标签。

## 7. Calibration Interpretation

- 自动指标只能证明 deterministic identity、offset、hard limit 与 raw filtering/overlap 行为。
- 自动指标不能证明一个 chunk 对业务问题是否 relevant，也不能判断 overlap 是否必要。
- `question_evidence_coverage >= 90%` 是首次校准目标，不是永久产品规则。
- 通常 1–3 chunks 应提供足够证据；若真实问题持续需要更多 chunks，应优先检查 fragmentation、
  duplicate content 与 section merge/split 参数，而不是直接增加 Retriever Top-K。
- Recall@K、MRR、nDCG 留给 R3 Retriever；在 query ranking 存在前使用这些指标会制造伪精度。

## 8. Stop Condition

R2a.1 Human Review 已完成。下一步执行 final gate，并依据
`docs/reports/R2a-final-human-evaluation-report.md` 的 `KEEP_CURRENT_CHUNKER` 决策完成 PR #34 merge。
R2b 仅保留规划，不实现 pgvector、embedding、retrieval、reranker 或 LLM generation。

## 9. Human Evaluation Progress

### Q1 — Main Products

- answerable：`YES`
- minimum chunks：`2`
- boundary finding：Candidate B 为 `BROKEN_BEFORE`
- short-chunk finding：Candidate B 为 `SHOULD_MERGE_PREVIOUS`

### Q2 — Fitness Relevance

- answerable：`PARTIAL`
- minimum chunks：`1`
- four candidates：全部 `PARTIALLY_RELEVANT`、`GOOD`、`NOT_APPLICABLE`
- missing evidence：缺少明确产品分类、完整产品目录或业务描述，不能绝对确认或排除
  fitness equipment / gym equipment。

### Q3 — Import / Distribution Evidence

- answerable：`YES`
- minimum chunks：`1`
- five candidates：全部 `RELEVANT`、`GOOD`、`NOT_APPLICABLE`
- evidence interpretation：一个包含完整进口事实的 Chunk 已足够；其余 4 个主要是重复信息。
- finding：`EVIDENCE_REDUNDANCY_OBSERVED`

### Q4 — China Supply-Chain Evidence

- answerable：`YES`
- minimum chunks：`1`
- candidate：`RELEVANT`、`GOOD`、`VALID_HEADING_CONTEXT`
- short-chunk finding：33 tokens 但语义完整，保留 `About Acme → Supply Network` 标题结构。
- finding：`VALID_SHORT_CHUNK_OBSERVED`

### Q5 — Product / HS Match Evidence

- answerable：`PARTIAL`
- minimum chunks：`1`
- candidate：`RELEVANT`、`GOOD`、`VALID_HEADING_CONTEXT`
- product evidence：18-token Chunk 完整保留 `Products` 标题结构和 Fasteners、Material Handling
  两组产品类别。
- missing evidence：`HS code / HS classification`
- finding：`VALID_SHORT_CHUNK_OBSERVED`
- finding：`RETRIEVAL_RELEVANT_BUT_INCOMPLETE_EVIDENCE`

### Q6 — Company Business Role

- answerable：`YES`
- minimum chunks：`1`
- candidate：`RELEVANT`、`GOOD`、`VALID_HEADING_CONTEXT`
- company-role evidence：Acme 提供 industrial fastener global sourcing and distribution。
- customer-role evidence：Acme 服务 importers、distributors 和 manufacturers；这描述客户群，
  不能推断 Acme 本身就是 importer。
- finding：`CUSTOMER_ROLE != COMPANY_ROLE`
- finding：`RETRIEVAL_RELEVANCE != CLAIM_ENTAILMENT`
- finding：`VALID_SHORT_CHUNK_OBSERVED`

### Q7 — Non-Target Business Evidence

- answerable：`NO`
- minimum chunks：`0`；evaluation 文件使用整数型字段，未修改 database schema。
- candidate：`NOT_RELEVANT`、`GOOD`、`VALID_HEADING_CONTEXT`
- entity metadata：location、founded year、team size 均为有效事实。
- missing evidence：缺少能够判断目标/非目标业务的主营业务、产品、服务或行业分类证据。
- finding：`ABSENCE_OF_EVIDENCE != EVIDENCE_OF_ABSENCE`
- finding：`ENTITY_RELEVANCE != QUESTION_RELEVANCE`
- finding：`VALID_SHORT_CHUNK_OBSERVED`

### Q8 — Page Fulfillment Capabilities

- answerable：`YES`
- minimum chunks：`1`
- candidate：`RELEVANT`、`GOOD`、`VALID_HEADING_CONTEXT`
- capability evidence：Cross-docking、Inventory storage、Pick and pack、Retail replenishment、
  Dealer delivery。
- question semantics：问题为“产品 或 履约能力事实”，无需同时存在产品 evidence。
- short-chunk threshold：23 tokens，符合 `<50` review threshold；未修改 threshold。
- finding：`SHORT_CHUNK != BAD_CHUNK`
- finding：`VALID_SHORT_CHUNK_OBSERVED`

### Q9 — Opportunity-Supporting Company Facts

- answerable：`YES`
- minimum chunks：`1`
- candidate：`RELEVANT`、`GOOD`、`VALID_HEADING_CONTEXT`
- company facts：Texas distribution center、Gulf ports 附近 receiving capacity、预期缩短
  imported industrial products 的 inland transit time。
- short-chunk threshold：32 tokens，符合 `<50` review threshold；未修改 Chunker 参数。
- unsupported judgments：成交概率、Opportunity score、客户价值、利润、当前货代关系和最终开发优先级。
- finding：`COMPANY_FACT != OPPORTUNITY_JUDGMENT`
- finding：`VALID_SHORT_CHUNK_OBSERVED`

### Q10 — Best Citation for Freight-Mode Claim

- answerable：`YES`
- minimum chunks：`1`
- Candidate A：`NOT_RELEVANT`、`GOOD`、`VALID_ATOMIC_FACT`、`NOT_ENTAILED`、`INSUFFICIENT`
- Candidate B：`RELEVANT`、`GOOD`、`VALID_ATOMIC_FACT`、`ENTAILED`、`SUFFICIENT`
- best citation：Candidate B，`12628577-8370-53be-b73c-5d731531c7ef`
- finding：`CHUNK_QUALITY != QUERY_RELEVANCE`
- finding：`QUERY_RELEVANCE != CLAIM_ENTAILMENT`
- finding：`CLAIM_ENTAILMENT != CITATION_SUFFICIENCY`
- finding：`BEST_CITATION = MINIMAL_SUFFICIENT_EVIDENCE`

### RETRIEVAL_REDUNDANCY_CANDIDATE

Q2 的 4 个约 500-token candidates 提供高度重复的信息。后续 Retrieval Evaluation 必须评估：

1. duplicate / near-duplicate retrieval rate
2. context redundancy ratio
3. unique evidence coverage
4. top-k diversity
5. 是否需要 MMR / deduplication / diversity reranking

这是后续 Retrieval 阶段的问题。本轮不修改 Chunker、chunk size、overlap 或 merge policy。

### EVIDENCE_REDUNDANCY_OBSERVED

Q3 的 5 个 candidates 不得被计为 5 份独立证据。最终 R2a Evaluation 必须区分：

1. source-level repetition：`OBSERVED`，fixture 原文重复同一句进口事实。
2. chunk overlap duplication：`OBSERVED`，后续 chunks 含约 70-token overlap。
3. chunker redundancy：`NOT_ISOLATED`，当前样本无法把冗余单独归因于 Chunker。
4. future retrieval redundancy：`NOT_EVALUATED`，当前没有 Retriever。

因此，本发现既不能直接触发 Chunker 参数修改，也不能提前归因于未来 Retrieval。

### RETRIEVAL_RELEVANT_BUT_INCOMPLETE_EVIDENCE

Q5 证明 retrieval relevance 与 answer completeness 是两个独立评测维度：

- Chunk 对产品匹配问题是 `RELEVANT`，应被未来 Retriever 命中。
- 当前 evidence 只能支持产品类别，不能支持 HS code / HS classification。
- Question-level answerability 因此为 `PARTIAL`，Grounded Answer 必须显式声明缺失 HS evidence。
- 不得因为 Chunk 很短或 evidence 不完整，就把该 Chunk 自动标记为不相关或自动合并。

这一发现仅记录 Evaluation 语义，不触发 target chunk size、hard max、overlap、tokenizer、
`structure-recursive-v1` 或 database schema 修改。

### CUSTOMER_ROLE != COMPANY_ROLE

Q6 的 `We serve importers` 是 customer-role evidence，不是 Acme 自身的 importer-role evidence。
Grounded Claim 必须保持主语、谓语和角色关系与原文一致，不能把客户类型转换为公司身份。

### RETRIEVAL_RELEVANCE != CLAIM_ENTAILMENT

Q6 的 Chunk 对 company business role 问题是 `RELEVANT`，但 relevance 只说明值得放入回答上下文。
最终 Claim 是否成立仍需单独验证 evidence entailment；正确检索到 evidence 不代表任意生成结论都被支持。

### ABSENCE_OF_EVIDENCE != EVIDENCE_OF_ABSENCE

Q7 没有提供非目标业务 evidence，因此当前问题不可回答。不得把“当前 evidence 未出现非目标业务”
转换成“公司不存在非目标业务”的结论。

### ENTITY_RELEVANCE != QUESTION_RELEVANCE

Q7 的 location、founded year 和 team size 都属于正确 Company，但它们对目标/非目标业务判断没有
判别价值。Entity scope 正确只是 retrieval filter，不能替代 query-specific relevance 判断。

### SHORT_CHUNK != BAD_CHUNK

Q8 的 23-token Chunk 通过标题层级保留 Warehousing 与 Distribution 两组完整能力事实。Chunk
质量应依据 semantic completeness、heading/context preservation、evidence independence 与
question answerability，而不能仅根据 token_count 判断。

### Evidence Redundancy Status after Q8

- Q2 `RETRIEVAL_REDUNDANCY_CANDIDATE`：保持不变。
- Q3 `EVIDENCE_REDUNDANCY_OBSERVED`：保持不变。
- Q8：单一候选，无 duplicate/near-duplicate evidence finding。

### COMPANY_FACT != OPPORTUNITY_JUDGMENT

Q9 明确验证 Evidence Layer 与 Decision Layer 的责任边界：Document → Chunk → Retrieval 产生
Grounded Facts；Business Rules / Scoring / Reasoning 再基于这些事实产生 Opportunity Tier、Score
或 Decision。事实相关且完整，不代表任何下游判断自动成立。

### Evidence Redundancy Status after Q9

- Q2 `RETRIEVAL_REDUNDANCY_CANDIDATE`：保持不变。
- Q3 `EVIDENCE_REDUNDANCY_OBSERVED`：保持不变。
- Q8/Q9：均为单一候选，没有新增 duplicate/near-duplicate evidence finding。

### Short Chunk Classification Split

当前必须区分：

- `SHORT_CHUNK_MERGE_CANDIDATE`：Q1 Candidate B，5 tokens，`BROKEN_BEFORE`，
  `SHOULD_MERGE_PREVIOUS`。
- `VALID_SHORT_CHUNK`：
  - Q1 Candidate A，11 tokens，`VALID_ATOMIC_FACT`。
  - Q4 Candidate A，33 tokens，`VALID_HEADING_CONTEXT`。
  - Q5 Candidate A，18 tokens，`VALID_HEADING_CONTEXT`。
  - Q6 Candidate A，27 tokens，`VALID_HEADING_CONTEXT`。
  - Q7 Candidate A，15 tokens，`VALID_HEADING_CONTEXT`；对当前 Query 为 `NOT_RELEVANT`，但内容本身有效。
  - Q8 Candidate A，23 tokens，`VALID_HEADING_CONTEXT`；结构完整的能力列表可独立引用。
  - Q9 Candidate A，32 tokens，`VALID_HEADING_CONTEXT`；完整保留设施事件与运营影响。

因此不得建立 `token_count < 50 => merge` 的简单规则。semantic completeness、标题上下文与
事实独立性必须优先于 fixed token length。
