# ADR-0029 — Cleaned content retention and immutable versioning

状态：**已批准**
日期：2026-08-09
相关：ADR-0026（本 ADR 只 supersede 其“网页全文不持久化”留存结论）

## 背景

ADR-0026 为 v0.2 安全抓取选择不保存第三方网页全文。Evidence-Grounded RAG 需要能够
复现 chunk、retrieval context 和 citation，因此必须保存受限的 cleaned text；同时不能把
raw HTML、脚本或无限正文引入数据库。

## 决策

### 1. 保存 cleaned text，不默认保存 raw HTML

`ResearchDocument.content` 只保存现有 `clean_html` 的输出，最大 40,000 字符。
raw HTML 只在当前 fetch 进程内用于 link extraction，不持久化。script、style、form、iframe、
navigation 和已识别 boilerplate 在保存前移除。

### 2. Content identity

- cleaned content 使用 UTF-8 SHA-256 `content_hash`。
- `canonical_url` 由 final URL 生成：去 fragment、tracking params、默认 port，host 规范化。
- URL identity 与 content identity 分开保存。

### 3. Immutable versions

- 同 company + canonical URL 的 current content hash 未变化：复用现有 Document。
- content 变化：创建新 Document；旧 Document 变为 `superseded`、`is_current=false`，
  新 Document 指向 `supersedes_document_id`。
- 历史 Document 的 id、content、hash、fetched_at 永不覆盖。
- 不同 URL 的相同 content 保留独立 provenance，并用 `duplicate_of_document_id` 指向同公司
  current content root，供 R2 默认跳过重复 chunk/index。
- 相同 hash 跨 Company 不共享 Document identity，也不能建立 duplicate/supersede link。

### 4. Concurrency

同 company + canonical URL 的 ingestion 使用 transaction-scoped PostgreSQL advisory lock，
同 company + content hash 也使用锁以稳定 duplicate root。数据库 additionally 使用 partial
unique index，保证每个 `(company_id, canonical_url)` 最多一个 current Document。

### 5. Retention 与删除

- `research_pages.document_id` 使用 `ON DELETE RESTRICT`。
- Document 的 originating ResearchRun、自引用 version/duplicate link 均使用 `RESTRICT`
  或 same-company composite FK。
- `company_id` 是 immutable corpus scope key，不新增指向 Company aggregate 的 FK；这样既保留
  跨 Company 隔离，也不改变既有 Company 删除后 ResearchRun 继续存活的生产语义。
- 已引用 Document 不能 cascade 删除。未来 retention job 必须先证明没有 page/claim/chunk
  引用，并保留审计要求的历史窗口。

### 6. Privacy 与安全

- 不保存 headers、cookies、credentials、raw HTML。
- JSON metadata 使用白名单生成的数据：content type、长度、截断、发现原因、meta description、
  quarantine reason。
- injection-like、thin 或超过 cleaned-text budget 后被截断的内容标记 `quarantined`；
  legacy extractor 行为 R1 不变，但未来 retrieval 只能读取 `ready` corpus。截断内容保留
  `truncated=true` 与 `content_truncated` quarantine reason，不得被视为完整 Document。
- failed fetch、oversized response、SSRF/redirect rejection 不创建 Document。

## 后果

- 数据库存储增加，但内容有硬上限且只限已确认 Company 的研究页面。
- 历史 citation 可复现，代价是不能通过覆盖或 cascade delete 简化清理。
- ADR-0026 的 SafeFetcher、URL Guard、budgets、robots 与 raw HTML 不持久化规则继续有效。
