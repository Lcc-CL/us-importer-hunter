# R2b — Retrieval Foundation Plan

日期：2026-08-11
状态：**PLAN_ONLY / NOT_STARTED**
前置基线：`RAG_CHUNKING_BASELINE_V1`
前置决策：R2a `KEEP_CURRENT_CHUNKER`

## 1. Objective

R2b 建立最小可评测 Retrieval foundation：

```text
ResearchDocumentChunk
→ Embedding
→ Vector Storage
→ Query Embedding
→ Top-K Retrieval
→ Retrieval Evaluation
```

R2b 的目标不是生成答案，而是证明：给定真实业务 Query，系统能稳定返回正确、足够且不过度重复的
evidence chunks。

## 2. Current Turn Boundary

本文件只做规划。本轮禁止实现：

- pgvector extension / index
- embedding provider
- document embedding job
- query embedding
- vector retrieval
- hybrid retrieval
- reranker / MMR
- LLM answer generation

R2b 实现必须在 R2a merge 后单独启动。

## 3. Proposed Deliverables

### R2b.1 — Embedding Contract

- 定义 provider-independent embedding interface。
- 明确 model name、dimension、normalization、batch size 与 timeout metadata。
- embedding identity 必须绑定 `chunk_id + embedding_model_version`。
- 不把 provider SDK 引入 Domain。

### R2b.2 — Vector Persistence

- PostgreSQL + pgvector 作为首选方向，遵循 ADR-0030。
- 新增 additive migration，不修改历史 migration。
- Chunk 仍是 source of truth；vector row 只保存可重建 projection。
- 明确 current Document、company scope 与 chunker/embedding version filter。

### R2b.3 — Embedding Workflow

- 只处理 eligible/current/ready chunks。
- batch idempotency、retry 与 partial failure 可观察。
- 不重复 embedding 相同 chunk/model identity。
- 不调用 LLM。

### R2b.4 — Query Retrieval

- Query → embedding → company-scoped Top-K vector search。
- 返回稳定 typed result：chunk identity、score、document provenance 与 citation metadata。
- 不在 route 中实现业务逻辑。

### R2b.5 — Retrieval Evaluation

- 从 `RAG_CHUNKING_BASELINE_V1` 派生首个 retrieval dataset。
- 保留 Human Ground Truth，不由系统自动生成 relevance label。
- 区分 query relevance、claim entailment 与 citation sufficiency。

## 4. Retrieval Metrics

R2b/R3 才允许正式计算：

- Recall@K
- MRR
- nDCG@K
- duplicate / near-duplicate retrieval rate
- context redundancy ratio
- unique evidence coverage
- top-k diversity
- citation-ready hit rate
- company/document scope violation count

Recall@K 不能单独作为成功标准。高 Recall 但 Top-K 全是重复 evidence，仍会浪费 context 并降低
Grounded Answer 质量。

## 5. Initial Evaluation Questions

优先复用 Q1–Q10，但必须为 retrieval 阶段补充：

- 每题 relevant chunk set
- preferred minimal citation set
- acceptable alternate chunks
- explicit non-relevant hard negatives
- company/document scope
- target K

Q2/Q3 必须重点验证 redundancy 与 top-k diversity。Q10 必须验证最佳 citation 是否能被排在
Supplier Overview 之前。

## 6. Versioning and Reproducibility

每次 evaluation run 必须记录：

- dataset version
- chunker version
- embedding model/version
- vector index configuration
- query normalization version
- retrieval algorithm/version
- K
- evaluated commit
- timestamp

Embedding 或 Retriever 参数变化不得覆盖旧结果。

## 7. Architecture Boundaries

- Domain 不依赖 pgvector、SQLAlchemy 或 embedding SDK。
- Repository 接收/返回 Domain 或 typed application contracts，不暴露 ORM Model。
- Provider 不访问 Repository。
- Workflow 编排 chunk eligibility、embedding 与 persistence。
- Retrieval service 只返回 evidence candidates，不产生 Opportunity judgment。
- Claim entailment 与 citation sufficiency 不能被 cosine similarity 替代。

## 8. Security and Cost Controls

- 明确 embedding request size 与 batch budget。
- 禁止发送未获授权的敏感内容给外部 provider。
- provider key 继续通过 settings 注入，不写入代码或 fixture。
- 为重试、限流和 provider failure 提供 typed failure reason。

## 9. Suggested Implementation Sequence

1. Review/approve R2b data contract and ADR delta。
2. Add embedding provider protocol and deterministic fake。
3. Add pgvector migration and repository projection。
4. Add idempotent chunk embedding workflow。
5. Add company-scoped Top-K retrieval service/API boundary。
6. Build retrieval evaluation runner and frozen dataset。
7. Run Recall@K/MRR/nDCG plus redundancy/diversity metrics。
8. Decide whether MMR, deduplication, hybrid search or reranking is justified。

## 10. Exit Gate

R2b 只有在以下条件满足后才能进入生成式 RAG：

- vector identity 与 chunk citation identity 可追溯
- scope violation = 0
- deterministic fake tests green
- real PostgreSQL migration lifecycle green
- relevant evidence retrieval 达到批准目标
- redundancy/diversity 风险有量化结果
- Human Ground Truth 未被自动 label 覆盖

R2b 不自动批准 hybrid retrieval、reranker 或 LLM generation；这些能力必须由 evaluation evidence
证明有必要。
