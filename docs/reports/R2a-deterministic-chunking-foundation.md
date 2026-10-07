# R2a — Deterministic Chunking Foundation

日期：2026-08-09
状态：**READY FOR REVIEW**
分支：`feat/rag-r2a-deterministic-chunking`

## 1. R1 Final Status

PR #33 在 final P0 audit 中发现 cleaned text 被 40,000-character cap 截断后仍可能进入
`ready` corpus。R1 最终采用 quarantine policy：`truncated=true`、quarantine reason
`content_truncated`，截断 Document 不得被后续 RAG 当作完整语料。

修复后 PR checks 通过，并 squash merge 到 `main`：
`6cfa69574bed979d8bc49ff26a6cd02c2a3fff17`。local main、origin/main 与 Alembic head 同步，
post-merge 1,288 backend tests、Ruff、strict mypy 与 drift check 全绿。

## 2. Scope

R2a 将 current + ready + non-duplicate `ResearchDocument` 转换为 deterministic、可持久化、
可重放、可引用的 `ResearchDocumentChunk`。本阶段没有 Retrieval、Embedding、pgvector、
Vector Search、LLM 或 paid provider 行为，也未接入生产 Research workflow 自动切块。

## 3. Chunk Domain Model

`ResearchDocumentChunk` 字段：

- `id`
- `document_id`
- `company_id`
- `chunk_index`
- `content`
- `content_hash`
- `token_count`
- `start_offset`
- `end_offset`
- `heading_path`
- `metadata`
- `chunker_version`
- `tokenizer_profile`
- `status`

Domain invariants：

- chunk index 非负，token count 为正，content 非空。
- content hash 必须匹配 UTF-8 SHA-256。
- offsets 必须满足 `0 <= start < end`。
- `document.content[start:end]` 必须与 chunk content 完全 round-trip。
- `ResearchDocumentChunk.create(document=...)` 从 parent 复制 company scope。
- chunker 与 tokenizer 必须有可记录 version/profile。

## 4. Stable Identity

Chunk ID 使用 UUID5，输入为：

```text
document_id
+ chunker_version
+ start_offset
+ end_offset
+ content_hash
```

Document immutable，因此相同 Document version、chunker version 与结构/content 重跑会得到相同
Chunk IDs、ordering 与 offsets。Document 更新会产生新 Document ID，自然隔离新旧 citation target。

数据库额外唯一约束：

- `(document_id, chunker_version, chunk_index)`
- `(document_id, chunker_version, start_offset, end_offset)`

## 5. Chunker Version and Token Profile

- algorithm：`structure-recursive-v1`
- tokenizer：`unicode-lexical-v1`
- default config：target 500、hard max 900、split overlap 80 tokens
- default version：`structure-recursive-v1:e89d30e35ee3`

`unicode-lexical-v1` 是 deterministic local tokenizer profile：英文/数字 lexical units、CJK 单字符
与标点由显式 regex 计数。它不是 provider billing token，不使用 `len(text) / 4`，也不声称与未来
embedding/generation model tokenizer 相同。

config 参数与 tokenizer profile 参与 SHA-256 fingerprint。任何 target/hard max/overlap/profile
变化都会产生新 chunker version，不会静默覆盖旧 sequence。

## 6. Structure-aware Strategy

Pipeline：

```text
source lines
→ heading / PDF page structure
→ deterministic boilerplate + duplicate filtering
→ adjacent short-section merge
→ complete section passthrough
→ oversized section sentence-aware split
→ bounded split-only overlap
→ stable Domain chunks
```

支持：

- Homepage
- About
- Product
- Capabilities
- Blog/News
- text PDF page markers
- generic text fallback

Markdown heading markers用于 deterministic fixtures；对实际 cleaned website text，短独立行 heuristic
提供 heading fallback。Chunk metadata 保存 source type、section type、heading path、page number、
merged heading paths、split reason、token budgets 与 overlap count。

贸易 evidence 未按普通网页逻辑切块；后续应使用 deterministic evidence projection。

## 7. Boundary and Overlap Policy

- 完整 heading section 在 hard max 内保持完整，不添加 overlap。
- 相邻短 sections 只有在合并后不超过 target 时才合并。
- 只有 oversized section 的连续切片允许 overlap。
- split 优先在 target 至 hard-max 区间寻找完整 sentence boundary。
- 无安全 sentence boundary 时使用 hard token boundary，仍不超过 hard max。
- next slice 优先复用不超过 configured overlap 的完整尾部句子。

测试验证 hard max、sentence boundary、bounded overlap、stable ordering 与 offset roundtrip。

## 8. Boilerplate and Duplicate Policy

Deterministic filters覆盖 legal/cookie/repeated CTA hints 与 exact repeated lines。它不调用 LLM，且
每个 plan 输出：

- `duplicate_ratio = duplicate_tokens / source_tokens`
- `boilerplate_ratio = boilerplate_tokens / source_tokens`
- `overlap_ratio = overlap_tokens / emitted_tokens`

Fixture 观测：

| Fixture | Duplicate Ratio | Boilerplate Ratio | Overlap Ratio |
| --- | ---: | ---: | ---: |
| long-paragraph | 0.0000 | 0.0000 | 0.1248 |
| oversized-section | 0.0000 | 0.0000 | 0.1070 |
| repeated-footer-nav | 0.1852 | 0.2222 | 0.0000 |
| other seven fixtures | 0.0000 | 0.0000 | 0.0000 |

这些只衡量处理行为，不代表 relevance、claim confidence 或事实质量。

## 9. Eligibility and Duplicate Reuse

- only current + ready Document can chunk。
- quarantined Document：`SKIPPED_INELIGIBLE`。
- superseded Document：保留历史 chunks，但不生成新 chunks。
- `duplicate_of_document_id` 非空：`SKIPPED_DUPLICATE`，默认复用 content root chunks。
- 不删除 duplicate Document provenance；Document/Page/source URL lineage 保持 R1 语义。

## 10. Persistence and Idempotency

新增 `research_document_chunks` table：

- composite FK `(document_id, company_id)` → `research_documents(id, company_id)`，`RESTRICT`。
- deterministic UUID primary key。
- sequence/offset unique constraints。
- content/hash/count/offset/status CHECK constraints。
- document 与 company indexes。
- JSONB heading path 与 metadata。

Repository 在 `(document_id, chunker_version)` 上获取 transaction-scoped PostgreSQL advisory lock。
若已有 sequence，必须与当前 deterministic plan 的 Chunk IDs 完全一致才返回 `REUSED`；不一致时
抛出 conflict，不静默覆盖 citation target。两个独立 session 并发执行时最终只有一个 sequence，
结果为一个 `CREATED` 与一个 `REUSED`。

数据库 composite FK integration test 证明 mismatched company chunk 被拒绝。

## 11. Fixtures and Human Relevance Experiment

R2a 继续保留 R1 的 10 条 ingestion/source fixtures，并新增 10 条 Chunking Evaluation v0 fixtures：

1. Homepage
2. About page
3. Product page
4. Blog/News
5. long paragraph
6. heading + list
7. very short sections
8. oversized section
9. repeated footer/nav
10. text PDF page boundaries

`docs/learning/experiments/L03-chunking-relevance-template.jsonl` 包含 10 个 research questions、
固定 Company 与 deterministic candidate chunk IDs。`human_relevant_chunk_ids` 全部为空，由 Leo
人工填写；Codex 未提供最终 relevance labels。

## 12. Offline Visualization

CLI：

```bash
cd apps/backend
uv run python scripts/visualize_research_chunks.py --case oversized-section
```

输出：chunk index、heading、token count、start/end offsets、overlap、content preview，以及
duplicate/boilerplate/overlap ratios。工具只读取 fixture 并运行 pure chunker，不访问数据库或网络。

## 13. Migration

Migration：`b2d4e6f8a0c1_add_research_document_chunks.py`

- additive only；未修改历史 migration。
- Alembic single head：`b2d4e6f8a0c1`。
- initial upgrade + integration tests：通过。
- downgrade to `a9f1c2d3e4b5`：通过。
- upgrade to head + repeated integration tests：通过。
- `alembic check`：no new upgrade operations。
- 未执行 `CREATE EXTENSION vector`，未新增 vector/embedding column。

## 14. Tests

Targeted coverage：

- stable UUID5 identity
- deterministic rerun and ordering
- offset roundtrip
- hard max and sentence boundary
- short-section merge
- split-only bounded overlap
- heading and PDF page preservation
- duplicate and boilerplate ratios
- local tokenizer profile
- cross-company identity isolation
- repository idempotency and concurrency
- parent supersede isolation
- quarantined/duplicate eligibility
- DB same-company composite FK
- mapper roundtrip
- migration lifecycle

结果：

- R2a targeted suite：`21 passed`。
- repeated PostgreSQL lifecycle suite：`6 passed`。
- full backend pytest：`1307 passed in 107.16s`。
- Ruff：`All checks passed!`
- strict mypy：`Success: no issues found in 445 source files`。

首次 full pytest 运行期间 OrbStack Docker daemon 停止响应，PostgreSQL probe 超时；重启 OrbStack
与项目 PostgreSQL 后，健康检查成功并完成上述 1,307 项全量通过。该问题属于本地基础设施，
未发现代码级 test failure。

## 15. Architecture and Legacy Gates

- Domain 无 SQLAlchemy、pgvector、OpenAI SDK 或 provider SDK 依赖。
- ORM/JSONB mapping 保持在 database layer。
- 未修改 Research Claim prompt、extractor、ClaimValidator、Opportunity、Routing、Suppression、
  ProspectBatch、Umail 或 EmailDraft 行为。
- 未修改前端。
- 未自动 chunk production Research workflow；R2a 是可调用的 foundation + persistence contract。
- 未调用真实 LLM、Embedding API 或 paid provider。

## 16. Known Debt and R2b Boundary

- 实际 cleaned HTML 只保留文本换行，heading level 为 heuristic；需要用人工 labels 评估误判。
- 表格、扫描 PDF/OCR 与贸易 evidence 需要 source-specific deterministic extraction，未在 R2a 扩展。
- duplicate Document 目前不生成 rows；未来 citation projection 需明确 duplicate source 如何映射 root chunks。
- token profile 不是 provider tokenizer；R2b/R3 绑定 embedding profile 时必须记录独立 tokenizer contract。
- relevance template 尚未由 Leo 标注，因此 R2a 不宣称 retrieval quality 达标。
- R2b 应先完成人工 label、chunk visualization review、参数比较与 release thresholds，再进入
  embedding/pgvector implementation；不得跳过 evaluation 直接上线 vector retrieval。

## 17. Acceptance

- [x] ResearchDocumentChunk Domain 与 stable ID。
- [x] deterministic source-aware structure chunker。
- [x] configurable/versioned target、hard max、overlap。
- [x] deterministic local token profile。
- [x] split-only bounded overlap。
- [x] duplicate/boilerplate/overlap metrics。
- [x] 10 条 Chunking Evaluation v0 fixtures。
- [x] 10 问无人工答案 relevance template。
- [x] offline visualization CLI。
- [x] additive migration、same-company FK、idempotent repository。
- [x] targeted/full/static/migration gates 全绿。
- [x] no pgvector、embedding、vector retrieval、LLM、paid provider。
