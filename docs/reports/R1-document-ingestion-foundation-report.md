# R1 — Document Ingestion Foundation Report

日期：2026-08-09
状态：**READY FOR REVIEW**
分支：`feat/rag-r1-document-ingestion-foundation`

## 1. Scope

R1 在现有 Research bounded context 内建立 durable、immutable、traceable、company-scoped
`ResearchDocument` corpus。它复用既有 Website Research 的 `SafeFetcher`、URL Guard、
redirect/private-IP 防护、response/decompression budget 与 `clean_html`，不建立第二套
Research domain。

本阶段明确未实现：Chunk、Embedding、pgvector schema、Vector Retrieval、Hybrid Search、
Reranker、真实 LLM/Embedding 调用、自动邮件发送。

## 2. Architecture

```text
ResearchRun (一次执行与审计)
  ├─ ResearchPage (一次 fetch record，可链接 document_id)
  ├─ ResearchClaim (保持现有 page citation 语义)
  └─ ResearchDocument (cleaned content 的 durable immutable version)
       └─ ResearchDocumentChunk (R2，尚未实现)
```

- `ResearchRun` 继续是现有 aggregate root，并拥有 pages、claims、rejections、promotions。
- `ResearchPage` 保存本次请求、最终 URL 与 fetch metadata，不承担跨 run 内容 identity。
- `ResearchDocument` 保存某 Company、某 canonical URL 的 cleaned content version。
- `ResearchClaim` 的 prompt、extractor、validator、evidence snippet、page position 均未改变。
- standalone research 的 `company_id=None` 不创建 company corpus。
- Repository 接受和返回 Domain objects；ORM row 不泄漏到应用层。
- Provider、Extractor 与 Website tool 均不访问 Repository。

## 3. ADR Decisions

- ADR-0028：锁定 ResearchRun、ResearchPage、ResearchDocument、未来 Chunk 与 Claim ownership。
- ADR-0029：锁定 cleaned text retention、immutable versioning、dedup、删除限制、隐私与上限。
- ADR-0030：将首个 vector store 方向改为 PostgreSQL + pgvector first；R1 只记录方向。
- 历史 ADR 未删除或改写；`docs/decision.md` 仅追加索引。

## 4. Document Model

`ResearchDocument` 字段：

- identity/scope：`id`、`company_id`、`research_run_id`
- provenance：`source_url`、`canonical_url`、`final_url`、`source_type`、`title`
- immutable content：`content`、`content_hash`、`fetched_at`、`cleaner_version`
- lifecycle：`status`、`is_current`、`superseded_at`
- lineage：`supersedes_document_id`、`duplicate_of_document_id`
- policy：`trust_level`、`metadata_json`

Domain invariants：

- content trim 后必须非空，且最多 40,000 字符。
- `content_hash` 必须等于 cleaned content 的 UTF-8 SHA-256。
- 新 Document 只能以 `ready` 或 `quarantined` current version 创建。
- superseded Document 必须 `is_current=false` 且有 UTC `superseded_at`。
- Document 不能 supersede 或 duplicate 自己。
- metadata 通过 defensive copy 暴露。

`company_id` 是不可变 corpus scope key。为保持既有 Company 删除后 ResearchRun 继续存活的
生产语义，R1 不新增 `ResearchDocument → Company` 外键；同 Company 约束由写入路径、查询条件、
advisory lock、partial unique index 与 composite self-FK 共同保护。

## 5. Schema and Migration

Migration：`a9f1c2d3e4b5_add_research_documents.py`

Additive schema：

- 新表 `research_documents`。
- `research_pages` 新增 nullable `document_id`，兼容历史 ResearchRun。
- `research_pages.document_id → research_documents.id ON DELETE RESTRICT`。
- `research_documents.research_run_id → research_runs.id ON DELETE RESTRICT`。
- supersede/duplicate 使用 `(document_id, company_id)` same-company composite FK。
- partial unique index：`(company_id, canonical_url) WHERE is_current`。
- supporting indexes：`(company_id, content_hash)`、`research_run_id`。
- status、source type、trust level、URL、content size、hash、lifecycle 均有数据库 CHECK。
- `metadata_json` 使用 JSONB，避免 SQLAlchemy `metadata` 保留名冲突。

Migration 验证：

- Alembic head：`a9f1c2d3e4b5`，single head。
- `upgrade → PostgreSQL integration tests → downgrade → upgrade → integration tests` 通过。
- 兼容性修正后再次执行 `downgrade → upgrade` 通过。
- `alembic check`：`No new upgrade operations detected.`
- 未创建 `vector` extension、vector column 或 embedding schema。

## 6. Dedup and Version Semantics

| 输入情况 | R1 结果 |
| --- | --- |
| 同 Company + 同 canonical URL + 同 content hash | 复用 current Document |
| 同 Company + 同 canonical URL + 内容变化 | 旧版 superseded，新建 current immutable version |
| 同 Company + 不同 URL + 相同 content | 保留新 provenance Document，链接 duplicate root |
| 不同 Company + 相同 content | 分离 identity，不建立 duplicate link |
| standalone research | 不创建 company corpus |
| failed/empty fetch | 不创建 Document |
| injection-like/thin content | 创建 `quarantined` Document，不进入未来 ready retrieval |

历史 Document 的 `id`、content、hash、originating run 与 fetched time 不被覆盖。

Canonical URL 规则：host/IDNA 小写规范化、移除 fragment、默认 port、尾部 slash 与 tracking
query，保留并排序业务 query 参数；redirect 后以 `final_url` 生成 canonical identity，同时保存
原始 `source_url` 与 `final_url`。

## 7. Concurrency Gate

R1 不使用脆弱的 read-then-insert 单层检查，而是三层防御：

1. transaction-scoped PostgreSQL advisory lock：`company_id + canonical_url`。
2. transaction-scoped PostgreSQL advisory lock：`company_id + content_hash`。
3. partial unique index：每个 `(company_id, canonical_url)` 最多一个 current Document。

锁键按稳定 SHA-256 映射为 signed 64-bit key，并按数值排序获取，减少多锁死锁风险。并发
PostgreSQL integration test 使用两个独立 session/UoW 同时写入相同 Company、URL、content，
最终只有一个 current row，两个调用返回同一 Document identity。

## 8. Security and Retention

- 继续复用 SafeFetcher；Provider 不自行 fetch URL。
- SSRF、DNS/private IP、redirect、oversized body、decompression budget 回归由既有 tool suite 覆盖。
- raw HTML、headers、cookies、credentials 不持久化。
- script、style、noscript、iframe、form、navigation 与识别的 boilerplate 在 cleaner 中移除。
- cleaned text 最大 40,000 字符，并保存 cleaner version 与 truncated metadata。
- injection-like content 与 thin page 进入 quarantine，而不是 ready corpus。
- failed fetch、空 cleaned content 与被 fetch budget 拒绝的响应不创建空 Document。
- page、originating run 与 version lineage 对 Document deletion 使用 `RESTRICT`。

## 9. Evaluation Fixtures

`tests/fixtures/rag/ingestion_sources.v0.json` 包含 10 条 deterministic ingestion/source fixtures：

1. same URL + same content
2. same URL + changed content
3. different URL + identical cleaned content
4. same content across Company A/B
5. tracking query canonicalization
6. redirect final URL
7. failed fetch
8. quarantined malicious content
9. oversized document
10. cleaned heading/list structure

这些是 RAG Evaluation v0 ingestion fixtures，不是 chunk relevance fixtures。R0 报告已做最小
勘误；正式 chunker 与 chunk evaluation 留给 R2。

## 10. Tests

新增/扩展覆盖：

- Domain invariants、immutable content、supersede lifecycle、metadata copy。
- Mapper roundtrip 与 `metadata_json` mapping。
- Repository create/read/list、dedup、refresh、history、duplicate、cross-company isolation。
- 两 worker concurrent idempotency 与 one-current constraint。
- Workflow page → document linking、quarantine、standalone no-corpus。
- Migration table/column expectations与完整生命周期。
- Legacy Company deletion、Research links、Claims、Routing、Opportunity、Umail、Draft 回归。

最终结果：

- R1 targeted tests：`54 passed`。
- Compatibility regression tests：`8 passed`。
- Full backend pytest：`1287 passed in 120.97s`。
- Ruff：`All checks passed!`
- strict mypy：`Success: no issues found in 438 source files`。
- PostgreSQL migration lifecycle：通过。
- Alembic drift check：通过。

全量测试曾发现新 Company FK 与既有 Company 删除语义冲突；R1 删除该跨 bounded-context FK，
保留 immutable `company_id` scope key 后，相关回归与全量门禁均通过。

## 11. Legacy Compatibility

- `RAG_RESEARCH_ENABLED=false` 为默认配置。
- Research prompt、real/fake extractor selection、ClaimValidator 语义与 Claim 输出未改变。
- Import、Entity Resolution、Prospect Routing、Suppression、ProspectBatch、Opportunity、Umail、
  EmailDraft 与人工审核行为未改变。
- 外部业务响应不变；内部新增 cleaned corpus 持久化与 page document link。
- 未修改前端。
- 未调用真实 LLM、Embedding API 或付费 Provider。

## 12. Known Debt and Design Trade-offs

- R1 Claim 仍是 page-cited；immutable document/chunk citation 留给 R2/R3 additive migration。
- `duplicate_of_document_id` 只标记同 Company 的 current content root；R2 决定重复内容是否跳过 chunk。
- quarantine 是 corpus eligibility gate，不改变 legacy extractor；R2 context builder 必须显式只读 ready。
- `company_id` 不使用 Company FK 是为保持已有删除兼容；未来 retention/privacy policy 需决定 Company
  删除后 corpus 的审计窗口与物理清理流程。
- Cleaner version 已记录，但 cleaner 改版后的 selective re-ingestion policy 尚未实现。
- PDF 与 trade evidence source type 仅预留 enum；R1 workflow 只接入现有网站 HTML 路径。

## 13. Learning Checkpoints

已创建：

- `docs/learning/notes/L01-rag-fundamentals-notes.md`
- `docs/learning/notes/L02-document-ingestion-notes.md`

模板只提供问题、实验、代码事实、测试结果与 Leo TODO；概念解释和认知修正保留 Leo 自己完成。

## 14. R1 Acceptance Criteria

- [x] 在现有 Research domain 内新增 durable ResearchDocument。
- [x] cleaned text retention、immutable version、supersede 与 provenance dedup。
- [x] 跨 Company identity 隔离。
- [x] PostgreSQL 并发写入最多一个 current version。
- [x] additive migration 与 nullable page link。
- [x] SafeFetcher/cleaner/security boundary 不绕过。
- [x] 10 条 ingestion/source fixtures。
- [x] Domain、mapper、repository、workflow、integration tests。
- [x] Claim、Routing、Opportunity、Umail、Draft 行为兼容。
- [x] `RAG_RESEARCH_ENABLED=false`。
- [x] 无真实 LLM/Embedding/paid provider 调用。
- [x] 未安装 pgvector，未实现 chunk/vector retrieval。
- [x] full pytest、Ruff、strict mypy、migration lifecycle 全绿。

## 15. Leo R1 Questions

以下问题由 Leo 自己回答，本报告不提供标准答案：

1. ResearchRun、ResearchPage、ResearchDocument 分别解决什么问题？
2. 为什么网页更新时不能直接覆盖旧 content？
3. 为什么 URL identity != content identity？
4. 为什么 failed fetch 不能保存成空 Document？
5. 为什么 R1 完全不需要 pgvector，但仍然已经属于 RAG 工程的一部分？

## 16. Next R2

R2 应聚焦 deterministic Document Chunking Foundation：定义 chunk ownership、稳定 chunk identity、
heading/path/offset metadata、chunker version、去重内容的 index eligibility，并建立正式 chunk relevance
fixtures 与离线评价。R2 仍应先完成 chunking/evaluation，再决定是否安装 pgvector 与启动 embedding
lifecycle；不得跳过 company-scoped retrieval isolation 和 release gate。
