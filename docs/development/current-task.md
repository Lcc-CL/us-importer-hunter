# Current Task: v0.3 Evidence-to-Draft 单公司闭环

**状态**: PASS；本批 MVP 已完成，尚未进入批量或真实数据源阶段
**分支**: `feat/v0.3-evidence-to-draft-flow`
**基线**: Stage 4A.4.3 `2d7ddb6`，已通过 merge commit `704f1a0` 合入并 push `main`
**日期**: 2026-07-21

## 已完成

- 新增内部接口 `POST /api/v1/companies/{company_id}/import-evidence/upload` 与当前结果查询接口。
- UTF-8 CSV（5MB / 5000 行上限）复用既有 Raw Record → Normalization → Entity Resolution →
  Quality → Aggregate → Promotion → Qualification 链路；同步处理小文件，不接外部网络。
- 原始记录、Shipment、Entity Match 与 Job 均持久化；重复 CSV 复用 Shipment、Aggregate、
  Promotion 和 Draft，不重复计分。
- Guided Flow 增加“补充进口证据”组件，展示记录/Shipment、质量、晋级信号、评分变化、
  Qualification、缺失证据与 Draft 状态；刷新后从数据库恢复。
- 已保存 Sender Profile 从浏览器自动恢复；已保存联系人从 Company 恢复。Qualified 且二者完整时
  调用既有幂等 Draft workflow，未达标时不生成 Draft。
- 示例文件：`fixtures/import-evidence/demo-hardware-imports.csv`，可生成 `import_activity`、
  `china_dependency`，并在证据充分时生成 `logistics_complexity`。

## 验证

- 后端定向测试 7 passed（其中 PostgreSQL API 集成 4 条）；Ruff 修改文件 PASS；相关模块
  mypy strict PASS。
- Frontend tsc、ESLint（0 error，5 个既有 warning）、production build PASS。
- 单条 Playwright Evidence-to-Draft 旅程 PASS，覆盖 Reload；隔离 E2E 数据库已删除。
- Alembic 保持单 head `b7f1c84a9d23`；本轮无 Migration、无真实 Provider 调用。

## 范围与下一步

- 未运行 1038 条后端全量、66 条 E2E 全量、flag-off 或 Migration roundtrip；留待 v0.3.0 发布门禁。
- 未实现 shipping_fit、批量任务、真实 ImportYeti、公开 API、登录权限或自动发送邮件。
- 下一步仅建议真实用户使用单公司 CSV 做人工审核测试；开始前先确认本分支已 push 且工作树 clean。
