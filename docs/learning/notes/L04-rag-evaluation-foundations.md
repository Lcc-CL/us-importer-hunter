# L04 — RAG Evaluation Foundations

日期：2026-08-11
基线：`RAG_CHUNKING_BASELINE_V1`

## 1. Chunk Quality

Chunk Quality 关注一个 Chunk 本身是否是清晰、完整、稳定、可引用的 evidence unit。判断时要看：

- 语义是否完整
- 主语、行为和对象是否被切断
- 标题层级是否保留必要上下文
- 是否混入过多独立主题
- 是否包含模板、噪音或无意义重复
- offset、identity 与 source provenance 是否可追溯

Chunk Quality 不回答“它是否适合当前 Query”。一个高质量 Chunk 仍然可能与某个问题无关。

## 2. Query Relevance

Query Relevance 关注 Chunk 是否对当前问题有判别价值。它是 **Query 与 Chunk 的关系**，不是 Chunk
的永久属性。

例如 Q10 Candidate A 是有效的日本供应来源事实，但 freight-mode Query 需要海运/空运 evidence，
所以它是 `NOT_RELEVANT`。这不代表 Candidate A 是坏 Chunk。

## 3. Claim Entailment

Claim Entailment 关注 evidence 是否在逻辑上支持一个具体 Claim。判断时要核对：

- 主体是否相同
- 行为是否相同
- 对象、时间、地点和限定条件是否一致
- Claim 是否增加了原文没有的推断

Q6 的 `We serve importers` 不能 entail “Acme is an importer”，因为 customer role 与 company role
不同。正确检索到相关 Chunk，也不代表生成的每个 Claim 都被支持。

## 4. Citation Sufficiency

Citation Sufficiency 关注引用的 evidence 是否足以让读者验证完整 Claim。一个 Chunk 可能支持 Claim
的一部分，但仍不足以作为唯一 citation。

例如产品 Chunk 可以支持产品类别，却不能支持不存在于页面中的 HS classification。此时 Chunk
仍是 relevant，但答案必须声明 evidence 不完整。

## 5. Minimal Sufficient Evidence

Minimal Sufficient Evidence 是能够直接、完整支持 Claim 的最小 evidence set。它避免：

- 引用过多无关上下文
- 把同一事实的重复 Chunk 当成多份证据
- 增加 LLM context noise
- 让 Human Reviewer 难以核验

Q10 Candidate B 单独完整支持 ocean/air freight Claim，因此它是最佳 citation；Candidate A 不需要
被一起引用。

## 6. 为什么 NOT_RELEVANT 不等于坏 Chunk

`NOT_RELEVANT` 只描述当前 Query。一个地点、成立年份或供应来源 Chunk 可能对公司画像很有价值，
但对 freight mode、产品类别或行业排除问题没有判别能力。

工程上必须保留：

`CHUNK_QUALITY != QUERY_RELEVANCE`

否则系统会错误删除对其他 Query 有价值的 evidence。

## 7. 为什么 Short Chunk 不等于坏 Chunk

短 Chunk 可能是：

- 完整的独立事实
- 结构清晰的产品列表
- 有标题保护的能力列表
- 精确的 citation target

R2a 中 10 个 `<50` token chunks 有 9 个被判断为有效 evidence units，只有 1 个建议合并。因此不得
建立 `token_count < 50 => merge` 规则。长度只是审查信号，不是质量结论。

## 8. Ground Truth

Ground Truth 是由 Human Reviewer 明确确认的预期标签和答案边界。本项目当前 Ground Truth 包括：

- relevance
- boundary quality
- short-chunk class
- question answerability
- minimum chunks required
- missing evidence
- claim entailment（Q10）
- citation sufficiency（Q10）
- best citation（Q10）

Ground Truth 必须版本化，并与具体 dataset、chunker version 和 evaluated commit 绑定。

## 9. Evaluation Dataset

Evaluation Dataset 不是一组随便挑选的文档，而是可重放的：

```text
Question
→ Candidate Evidence
→ Human Ground Truth
→ Metrics
→ Engineering Decision
```

好的 dataset 既要有正例，也要有 hard negatives、重复 evidence、短文档、长文档和边界压力场景。

## 10. 为什么 Evaluation 要先于参数调优

没有 baseline 时修改 chunk size 或 overlap，只能得到“看起来更好”的主观感觉，无法判断：

- 哪些问题真的改善
- 哪些 citation identity 发生 regression
- evidence coverage 是否下降
- redundancy 是否增加
- short facts 是否被错误合并

因此任何参数变化都必须先提出假设，再与 `RAG_CHUNKING_BASELINE_V1` 对比。

## 11. 为什么 10 Fixtures 是 Baseline 而不是 Production Proof

10 个 fixtures 足以验证评测流程是否可运行，并暴露第一批工程问题，但无法覆盖真实网页的长尾：

- 不同 CMS 与导航模板
- 大型 catalog 和复杂 table
- 双语/多语页面
- PDF OCR 噪音
- FAQ、新闻和物流页面
- 极短与极长文档
- boilerplate-heavy 页面

因此当前结论是 `KEEP_CURRENT_CHUNKER` 作为工程 baseline，而不是“Chunker 已达到 production
optimal”。后续 dataset 应按 `10 → 50 → 100+` 扩展，但不阻塞 R2a merge。

## 最终记忆卡

```text
Chunk Quality != Query Relevance
Query Relevance != Claim Entailment
Claim Entailment != Citation Sufficiency
Best Citation = Minimal Sufficient Evidence
Short Chunk != Bad Chunk
Evaluation Before Parameter Tuning
```
