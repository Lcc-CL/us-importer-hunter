# R2a Final Human Evaluation Report

日期：2026-08-11
状态：**R2A_FINAL_EVALUATION_COMPLETE**
Baseline：`RAG_CHUNKING_BASELINE_V1`
评测代码提交：`24382397a00bf573db02e73f2a7fad2adc22ee7e`
分支：`feat/rag-r2a-deterministic-chunking`
PR：`#34`

## 1. Executive Decision

**Decision：`KEEP_CURRENT_CHUNKER`**

Q1–Q10 Human Ground Truth 没有证明当前 Chunker 存在系统性 semantic truncation、evidence loss、
over-chunking 或 under-chunking。19 个 candidate chunks 中只有 Q1 Candidate B 出现一次
`BROKEN_BEFORE / SHOULD_MERGE_PREVIOUS`；该问题仍可由 2 个 chunks 完整回答，事实没有丢失。

因此本轮不修改：

- `target_tokens=500`
- `hard_max=900`
- `overlap_max=80`
- `tokenizer=unicode-lexical-v1`
- `chunker=structure-recursive-v1`

## 2. Baseline Scope

本报告把 Q1–Q10 定义为 **`RAG_CHUNKING_BASELINE_V1`**。它用于：

1. 验证 Human Evaluation framework。
2. 建立第一组可重放 Ground Truth。
3. 为未来任何 Chunker 修改提供对比基线。

它**不证明**“10 个 fixtures 已使 Chunker 达到 production optimal”。

## 3. Dataset Summary

| Item | Result |
|---|---:|
| `questions_total` | `10` |
| `chunks_reviewed` | `19` |
| fixtures | `10` |
| answerable questions | `9` |
| unanswerable questions | `1` |

## 4. Human Evaluation Metrics

| Metric | Result | Interpretation |
|---|---:|---|
| `evidence_coverage` | `90.00%` (`9/10`) | YES 或 PARTIAL |
| `complete_answer_rate` | `70.00%` (`7/10`) | YES |
| `partial_answer_rate` | `20.00%` (`2/10`) | PARTIAL |
| `unanswerable_rate` | `10.00%` (`1/10`) | NO |
| `average_minimum_chunks` | `1.11` | 仅 9 个 YES/PARTIAL；Q7 存储值 0 不计入 |
| `median_minimum_chunks` | `1` | answerable-only |
| `max_minimum_chunks` | `2` | Q1 |
| `boundary_break_count` | `1` | Q1 Candidate B |
| `short_chunk_merge_candidate_count` | `1` | Q1 Candidate B |
| `valid_short_chunk_count` | `9` | 10 个 `<50` chunks 中 9 个有效 |
| `minimal_sufficient_evidence_cases` | `6` | Q3/Q4/Q6/Q8/Q9/Q10 |
| `evidence_redundancy_cases` | `1` | Q3 |
| `retrieval_redundancy_cases` | `1` provisional candidate | Q2；尚无 Retriever |

## 5. Label Distributions

### Relevance

| Label | Count |
|---|---:|
| `RELEVANT` | `13` |
| `PARTIALLY_RELEVANT` | `4` |
| `NOT_RELEVANT` | `2` |

### Boundary

| Label | Count |
|---|---:|
| `GOOD` | `18` |
| `BROKEN_BEFORE` | `1` |
| `BROKEN_AFTER` | `0` |
| `BROKEN_BOTH` | `0` |

### Short Chunk Classification

| Label | Count |
|---|---:|
| `NOT_APPLICABLE` | `9` |
| `VALID_ATOMIC_FACT` | `3` |
| `VALID_HEADING_CONTEXT` | `6` |
| `SHOULD_MERGE_PREVIOUS` | `1` |
| `FRAGMENTED` | `0` |
| `BOILERPLATE` | `0` |
| `SHOULD_MERGE_NEXT` | `0` |

### Claim Entailment

| Label | Count |
|---|---:|
| `ENTAILED` | `1` |
| `NOT_ENTAILED` | `1` |
| `NOT_EVALUATED` | `17` |

Q1–Q9 没有显式 claim-entailment Human Label，因此禁止追溯推断。

### Citation Sufficiency

| Label | Count |
|---|---:|
| `SUFFICIENT` | `1` |
| `INSUFFICIENT` | `1` |
| `NOT_EVALUATED` | `17` |

Citation sufficiency 仅在 Q10 显式标注。

## 6. Automatic Metrics

| Metric | Result | Target |
|---|---:|---:|
| `hard_limit_violation` | `0` | `0` |
| `offset_roundtrip_error` | `0` | `0` |
| `stable_identity_rate` | `100%` (`19/19`) | `100%` |
| aggregate raw `boilerplate_ratio` | `0.15%` | `<10%` calibration target |
| aggregate raw `duplicate_ratio` | `0.13%` | observe/minimize |
| aggregate raw `overlap_ratio` | `11.14%` | `<15%` initial target |

## 7. Q1–Q10 Ground Truth Summary

| Question | Answerable | Min Chunks | Main Finding |
|---|---|---:|---|
| Q1 Main Products | `YES` | `2` | 一个 5-token 产品卡 `BROKEN_BEFORE`，建议与前一 Chunk 合并 |
| Q2 Fitness Relevance | `PARTIAL` | `1` | 4 个候选高度重复；缺少明确产品分类 |
| Q3 Import/Distribution Evidence | `YES` | `1` | importer evidence 充分；重复 Chunk 不是独立证据 |
| Q4 China Supply Chain | `YES` | `1` | 33-token Chunk 是有效标题上下文 |
| Q5 Product/HS Match | `PARTIAL` | `1` | 产品 evidence 相关，但缺少 HS classification |
| Q6 Company Role | `YES` | `1` | customer role 不能转换成 company role |
| Q7 Non-Target Business | `NO` | `0` stored | entity metadata 与当前 Query 无判别关系 |
| Q8 Fulfillment Capabilities | `YES` | `1` | 23-token 结构化列表是独立 Retrieval Unit |
| Q9 Opportunity Facts | `YES` | `1` | Company Facts 是 Opportunity 输入，不是判断 |
| Q10 Best Citation | `YES` | `1` | Logistics Chunk 是 minimal sufficient citation |

完整逐 Chunk Ground Truth 位于：

- `docs/learning/experiments/L03-chunking-human-review-compact.md`
- `docs/learning/experiments/L03-leo-review-handoff.md`
- `docs/learning/experiments/RAG_CHUNKING_BASELINE_V1.json`

## 8. Chunker Assessment

### Systematic Semantic Truncation

**未观察到。** 只有 Q1 Candidate B 出现一次 `BROKEN_BEFORE`，没有形成跨 fixture 的系统模式。

### Evidence Loss

**未观察到。** 所有必要事实仍存在于 emitted chunks；Q1 需要两个 chunks，但 evidence 没有丢失。

### Over-Chunking

**存在一个 isolated candidate，但不系统。** Q1 的 5-token 产品卡应视为 merge candidate；没有证据支持
全局增加 minimum chunk size 或自动合并所有短 Chunk。

### Under-Chunking

**未观察到。** 没有 Human Label 标记 `CHUNK_TOO_LARGE_OR_MIXED`，也没有单个 Chunk 被认为混入
过多独立主题。

### Short Chunks

10 个 `<50` token chunks 中，9 个被 Leo 判断为 `VALID_ATOMIC_FACT` 或
`VALID_HEADING_CONTEXT`，只有 1 个为 `SHOULD_MERGE_PREVIOUS`。因此：

- `SHORT_CHUNK != BAD_CHUNK`
- 不应新增 `token_count < 50 => merge` 规则
- 不应仅凭长度设置强制 minimum chunk size

### Overlap and Redundancy

Q2/Q3 暴露重复 evidence，但当前 attribution 同时包含 source-level repetition、oversized-section
overlap 与未来 retrieval ranking 问题。`raw_overlap_ratio=11.14%` 低于初始 15% target，且尚无
Retriever，因此没有充分证据修改 `overlap_max=80`。

## 9. Parameter Decisions

| Parameter / Policy | Decision | Evidence |
|---|---|---|
| `target_tokens=500` | KEEP | 无系统性 fragmentation 或 mixed-topic evidence |
| `hard_max=900` | KEEP | 0 hard-limit violations；无 under-chunking label |
| `overlap_max=80` | KEEP | raw 11.14%；冗余 causality 未隔离 |
| `unicode-lexical-v1` | KEEP | stable deterministic profile；0 offset failures |
| `structure-recursive-v1` | KEEP | 18/19 boundaries GOOD；identity 100% |
| 增加 minimum chunk size | REJECT FOR NOW | 9/10 short chunks 是有效 evidence units |
| 自动 merge short chunks | REJECT FOR NOW | 仅 Q1 一个 merge candidate |

## 10. Core Engineering Findings

- `RETRIEVAL_RELEVANCE != ANSWER_COMPLETENESS`
- `CUSTOMER_ROLE != COMPANY_ROLE`
- `ABSENCE_OF_EVIDENCE != EVIDENCE_OF_ABSENCE`
- `ENTITY_RELEVANCE != QUESTION_RELEVANCE`
- `SHORT_CHUNK != BAD_CHUNK`
- `COMPANY_FACT != OPPORTUNITY_JUDGMENT`
- `CHUNK_QUALITY != QUERY_RELEVANCE`
- `QUERY_RELEVANCE != CLAIM_ENTAILMENT`
- `CLAIM_ENTAILMENT != CITATION_SUFFICIENCY`
- `BEST_CITATION = MINIMAL_SUFFICIENT_EVIDENCE`

## 11. Known Failure and Redundancy Cases

### Known Failure

- Q1 Candidate B：5 tokens，`BROKEN_BEFORE`，`SHOULD_MERGE_PREVIOUS`。
- 影响：Q1 仍可完整回答；这是 baseline known failure，不足以证明全局参数需要修改。

### Evidence Redundancy

- Q3：5 个 candidates 主要表达相同 importer fact。
- 必须区分 source repetition、chunk overlap 与 chunker-only causality。

### Retrieval Redundancy Candidate

- Q2：4 个约 500-token candidates 高度重复。
- 当前无 Retriever，不能声称已经测得 retrieval redundancy rate。
- R2b/R3 必须评估 duplicate/near-duplicate retrieval rate、context redundancy ratio、unique
  evidence coverage、top-k diversity 与 MMR/dedup/diversity reranking 的必要性。

## 12. Evaluation Limitations

当前 10 个 fixtures 是 baseline，不是 production proof。后续 Evaluation Dataset 应扩展：

`10 → 50 → 100+ examples`

并覆盖：

- product pages
- company about pages
- FAQ
- catalog
- tables
- news
- logistics pages
- short documents
- long documents
- boilerplate-heavy pages
- bilingual pages

该扩展是后续技术债，不阻塞 R2a merge。

## 13. Change-Control Rule

以后任何 Chunker 修改必须：

1. 产生新的 chunker version/fingerprint。
2. 与 `RAG_CHUNKING_BASELINE_V1` 使用相同 Ground Truth 对比。
3. 报告 quality gain 与 regression。
4. 不得仅凭个别样本或主观感觉修改参数。

## 14. R2a Merge Gate

最终本地 gate 结果：

| Gate | Result |
|---|---|
| targeted chunking/ingestion/mapper/PostgreSQL/migration tests | `32 passed` |
| full pytest | `1307 passed in 92.05s` |
| Ruff | `All checks passed` |
| strict mypy | `Success: no issues found in 445 source files` |
| Alembic heads | `b2d4e6f8a0c1 (head)`，单一 head |
| Alembic current | `b2d4e6f8a0c1 (head)` |
| Alembic drift | `No new upgrade operations detected` |
| migration lifecycle | empty → upgrade head → downgrade base → upgrade head，passed |
| chunk identity determinism | passed |
| PostgreSQL ingestion/chunk integration | passed |

本地状态：**`MERGE_READY`**。PR #34 只在 push 后 GitHub remote checks 仍为 green 且无 blocker 时执行
Squash Merge。Merge 不部署新的 production behavior；R2a 仍是 Evidence-Grounded RAG foundation。
