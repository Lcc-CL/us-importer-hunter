# ADR-0030 — PostgreSQL + pgvector first direction

状态：**已批准（方向）**
日期：2026-08-09
相关：ADR-0007、ADR-0013、R0 RAG Architecture Audit

## 背景

早期架构把 Qdrant 作为未来 RAG/long-term memory 的占位方向。当前系统的 Company、
Research、Evidence Review、Opportunity 与 Worker 均已落在 PostgreSQL，且 RAG 首个范围
严格限定为每批最多 5 家 A Tier Company。新增独立向量基础设施会提前引入双写、过滤和
运维复杂度。

## 决策

US Importer Hunter 的首个 Vector Store 方向为 **PostgreSQL + pgvector**，并在同一数据库
中评估 PostgreSQL Full Text Search 作为 Hybrid Retrieval 的 lexical lane。

本 ADR supersede ADR-0007/0013 中“RAG 默认使用 Qdrant”的规划方向，但不修改历史 ADR，
也不否定未来在量化容量、延迟、独立扩缩或 extension 限制下迁移 dedicated vector store。

R1 只记录方向：

- 不安装 pgvector。
- 不执行 `CREATE EXTENSION vector`。
- 不增加 vector column、embedding model 或 retrieval code。
- Embedding lifecycle、dimension、company-scoped retrieval isolation 和 evaluation release gate
  在 R2/R3 基于真实实现分别 finalize ADR。

## 后果

- R1 仅建立 Document corpus，没有任何 Vector RAG 运行行为。
- R2 必须先验证 local/test/production PostgreSQL extension availability，再创建 Migration。
- 如果 production 不支持 pgvector，任务应 BLOCK 并重新评估，不得静默切换实现。
