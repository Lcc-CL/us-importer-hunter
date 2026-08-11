# ADR-0031 — Deterministic ResearchDocument chunking contract

状态：**已批准**
日期：2026-08-09
相关：ADR-0028、ADR-0029、ADR-0030

## 背景

R1 已建立 immutable cleaned `ResearchDocument` corpus。后续 citation 与 retrieval 需要稳定、
可重放、可解释的 retrieval unit；随机 chunk ID、不可追溯 token 估算或 semantic chunking 会让
同一 Document 重切后无法复现 citation，也无法可靠比较 evaluation。

## 决策

### 1. Ownership

`ResearchDocumentChunk` 是 `ResearchDocument` 的持久化子资源。每个 Chunk 必须保存 parent
`document_id` 与相同 `company_id`；数据库通过 composite FK 强制 same-company ownership。
Chunk 不拥有 Claim，也不保存 embedding。

### 2. Stable identity

Chunk ID 使用 UUID5，由以下稳定输入计算：

- immutable `document_id`
- `chunker_version`
- `start_offset`
- `end_offset`
- chunk `content_hash`

同一 Document version、同一 chunker version 与同一结构/content 重跑会得到相同 sequence 与
Chunk IDs。数据库同时唯一约束 `(document_id, chunker_version, chunk_index)` 和 offsets。

### 3. Strategy

R2a 使用 deterministic、source-aware structure chunking：

1. heading/page/line structure extraction
2. deterministic boilerplate 与重复行过滤
3. 相邻短 section 在 token target 内合并
4. 完整 section 在 hard max 内保持完整且不 overlap
5. 只有超长 section 才按 sentence boundary 递归拆分
6. 无安全 sentence boundary 时才在 token boundary 执行 hard split

Homepage、About、Product、Capabilities、News、text PDF 与 generic text 共用可复现算法，但保留
source type、section type、heading path 与 PDF page number metadata。贸易 evidence 不走普通网页
chunking，留给单独 deterministic projection。

### 4. Token profile and versioning

R2a 不绑定 provider tokenizer。使用 `unicode-lexical-v1` 本地 profile：英文/数字 lexical unit、
CJK 单字符与标点均由明确 regex 计数。它不是 provider billing token，也不得冒充模型 token。

默认初值：target 500、hard max 900、split overlap 80 tokens。配置参与 SHA-256 fingerprint，形成
`structure-recursive-v1:<fingerprint>` chunker version；参数变化必须产生新 version。

### 5. Overlap and quality metrics

完整结构块不 overlap。只有 oversized section 的连续切片使用 bounded overlap，并优先复用完整
句子。每次 plan 输出：

- duplicate ratio
- boilerplate ratio
- overlap ratio

这些指标用于离线 evaluation，不代表 relevance 或事实质量。

### 6. Eligibility and idempotency

- 只有 current + ready Document 可以 chunk。
- quarantined 与 superseded Document 不生成新 chunks。
- `duplicate_of_document_id` 非空的 Document 默认复用 content root chunks，不重复持久化。
- Repository 使用 transaction advisory lock；已有 sequence 必须与 deterministic plan 完全一致，
  否则报告 conflict，不静默覆盖历史 citation target。

## 后果

- R2a 已建立稳定 citation target，但没有 retrieval、embedding 或 pgvector 行为。
- Document 更新产生新 Document ID，因此新版本 chunks 与历史 chunks 自然隔离。
- 未来修改 chunk 算法或参数必须产生新 chunker version，并经过固定 relevance labels evaluation。
- 未来 retrieval 必须同时检查 parent Document eligibility 与 company scope。
