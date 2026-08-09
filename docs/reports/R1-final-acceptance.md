# R1 — Final Acceptance

日期：2026-08-09
范围：PR #33 final P0 audit
结论：**ACCEPTED FOR SQUASH MERGE**

## 1. 40,000-character cap

`clean_html` 在 40,000 字符处停止保存正文。最终审计发现截断标记原本只写入 metadata，
Document 仍可能进入 `ready` corpus。R1 最终修复选择 quarantine policy：

- `truncated=true` 保留在 Document metadata。
- quarantine reason 增加 `content_truncated`。
- truncated Document 状态必须是 `quarantined`。
- 未来 chunk/retrieval 只允许处理 `ready` Document。

回归测试证明保存内容仍受 40,000 字符硬上限约束，且不会被标记为完整 ready corpus。

## 2. Duplicate provenance

不同 canonical URL 的相同 cleaned content 仍创建不同 Document identity，并保留各自：

- `source_url`
- `canonical_url`
- `final_url`
- originating `research_run_id`
- `ResearchPage.document_id`
- `company_id`

`duplicate_of_document_id` 只提供同 Company content lineage，不删除来源，也不跨 Company 复用。

## 3. Current-version concurrency

数据库层存在两项独立 gate：

- transaction-scoped PostgreSQL advisory lock，覆盖 Company + canonical URL 与 Company + hash。
- partial unique index `uq_research_documents_one_current_url`，约束
  `(company_id, canonical_url) WHERE is_current`。

两个独立 session/UoW 的并发 PostgreSQL integration test 最终只产生一个 current Document。

## 4. Domain boundary

`app/domain/research/document.py` 不依赖 SQLAlchemy、pgvector、OpenAI SDK 或 provider SDK。
Repository protocol 接受和返回 Domain objects；ORM 与 JSONB mapping 位于 database layer。

## 5. Legacy regression

R1 没有改变 CSV/XLSX deterministic parsing、Entity Resolution、Prospect Routing、Suppression、
Opportunity、Research Claim、ClaimValidator、Umail 或 EmailDraft 语义。新增行为仅为 company-scoped
cleaned corpus persistence 与 page-to-document audit link。

## 6. Merge gate

- PR #33 scope 未扩大到 Chunk、Embedding、pgvector、Vector Search、LLM 或 paid provider。
- R1 targeted、full pytest、Ruff、strict mypy、Alembic lifecycle 与 GitHub checks 必须在最终
  truncation fix 后重新通过，方可 squash merge。
- R2a 必须从 squash merge 后的最新 `main` 创建，并保持无 Embedding/pgvector 范围。
