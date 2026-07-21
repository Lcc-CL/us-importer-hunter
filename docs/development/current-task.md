# Current Task: Stage 4A.4.2 Corrective Closure

**状态**: PASS；Stage 4A.4.2 已完成，Stage 4A.4.3 尚未开始

**分支**: `feat/v0.3-import-evidence-agent`

**实现提交**: `dd58e30`

**测试提交**: `66f5d8d`

**日期**: 2026-07-21

## 接管差异与重开原因

交接报告称 `69103ee` 已完成 Stage 4A.4.2，但仓库实际仅有 Quality Assessment
和 Importer Aggregate 的领域计算及内存测试，缺少 Quality、Aggregate、Inclusion
的数据库模型、Migration、Repository/UoW、持久化 Workflow、历史查询和 reload 闭环，
因此重新打开 Stage 4A.4.2。本轮未进入 Signal Promotion。

## 已完成

- 新增 corrective Migration `a42c9e81f6b0`，创建：
  `import_evidence_quality_assessments`、`importer_evidence_aggregates`、
  `importer_evidence_aggregate_shipments`。
- Domain Model、Mapper、Repository Protocol、SQLAlchemy Repository、Unit of Work、
  Application/Query Service 和 Workflow 已形成完整持久化链路。
- Quality 与 Aggregate 支持 stable ID reload、current 查询、完整历史、相同输入零新增、
  输入变化生成新版本和旧版本 supersede；历史 fingerprint 再出现时复用并恢复为 current。
- Aggregate Workflow 强制读取每票 Shipment 当前已持久化 Quality，避免旧 Assessment 或调用方
  伪造质量状态进入 Aggregate。
- Inclusion 保存 Shipment、当前 Quality、业务 fingerprint、纳入状态/原因和跨 Provider 数量；
  FK 和唯一约束防止孤儿与重复业务 Shipment。
- 集中状态决策覆盖 READY、PARTIAL、INSUFFICIENT_DATA、BLOCKED；未生成任何 Signal。

## Fingerprint 与边界

- Quality fingerprint 基于版本、业务 Shipment fingerprint、来源数量、五维评分、状态、
  blockers/penalties 和参考日期。
- Aggregate fingerprint 基于 aggregate/rule version、规范化 importer identity、resolved 状态、
  as-of/window 以及排序后的 Shipment fingerprint + 当前 Quality fingerprint + entity/dedupe 状态。
- 不包含 provider、provider_record_id、数据库 ID、job_id、raw payload hash、创建时间或容器原始顺序；
  NULL-safe、输入顺序无关，Shipment/Quality/rule 变化会改变 fingerprint。
- 90/365/730 天均为闭区间；current/previous 365 不重叠；保留 customs business date，
  future date、身份冲突、rejected/separate、insufficient identity 会 BLOCKED。
- Shipment 跨 Provider 只计一次；Container 仅在各 Shipment 内去重，不跨 Shipment 去重；
  needs_review 可计算但不可晋级，company 未解析时 `promotable=false`。

## 验证结果

- PostgreSQL 集成测试：7 个测试，覆盖需求列出的 22 个持久化、版本、时间、去重、实体、
  FK 和 reload 场景。
- 后端：1009 passed；Ruff PASS；mypy strict 272 files PASS。
- 前端：tsc PASS；ESLint 0 error（5 个既有 warning）；production build PASS。
- E2E：66 passed；flag-off PASS；Migration upgrade/downgrade/upgrade PASS；Alembic 单 head。
- 开发库业务表行数与逐行内容 hash 均与接管前一致：companies 12、company_sources 27、
  company_signals 99、opportunities 12、opportunity_assessments 18、contacts 12、
  contact_fit_assessments 14、email_drafts 8、research_runs 52；全部 import evidence 表为 0。
- 隔离测试数据库已清理；未修改 Qualification 历史、权重或 70 分门槛。

## 已知限制与下一步

- 本阶段只闭合持久化与确定性 Aggregate，不调用真实 ImportYeti/付费数据、LLM 或邮件发送。
- 下一步可进入 Stage 4A.4.3 Deterministic Signal Promotion，但必须作为独立阶段启动。
- 禁止 merge main、创建 tag、自动发送邮件、修改 Qualification 权重/门槛或自动选择联系人。
