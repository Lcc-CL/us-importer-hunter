# D5d1 — 已确认 A 类 ProspectBatch 显式启动深度处理

日期：2026-08-02
分支：`feat/routing-batch-deep-processing-start`
目标提交：`feat(pipeline): start deep processing from routed prospect batches`
目标 PR：`feat(pipeline): add explicit deep-processing start for routed A prospects`

## 1. 实现结论

D5d1 已完成：D5c 创建但未启动的 routing-source `ProspectBatch`，现在必须由用户再次
显式确认，才会创建现有 `ProspectJob` 并交给 PostgreSQL worker 执行既有深度链路。
流程保留 Research Evidence 人工闸门、Resume、retry、heartbeat 与 stale recovery；
Draft 只生成并等待人工审核，不自动批准，不创建发送结果，也不发送邮件。

本轮未实现 B 类 Umail 导出、Suppression、结果回传、发送、Follow-up、Calibration、
邮箱验证、新 Provider、Celery 或其它任务系统。

## 2. D5c 修复与合并状态

D5c PR #7 的路由历史审计问题已修复：`ProspectRoute` 按
`routing_run_id + execution_generation + company_id` 分代不可变；重算不删除历史 Route，
历史 confirm/override/exclude、旧 Batch generation 与来源 hash 均保留。PR #7 已通过门禁并
Squash Merge；最新 `main`/`origin/main` 提交为
`522fbe6fd8158a31d5525d8015516ff5705fab4f`。PR #4 Calibration 未修改、未合并。

## 3. Git / PR

- 基线：`522fbe6 feat(routing): add auditable A/B/C/D prospect routing (#7)`。
- D5d1 分支：`feat/routing-batch-deep-processing-start`，从上述最新 main 创建。
- Commit message：`feat(pipeline): start deep processing from routed prospect batches`。
- PR 标题：`feat(pipeline): add explicit deep-processing start for routed A prospects`。
- D5d1 PR 只创建、不合并；GitHub URL 以该分支创建后的 PR 记录为准。
- 未创建 release tag，未触碰 PR #4。

## 4. Typed Batch source 设计

新增纯 Domain union `ProspectBatchSourceContext`，明确只有两种来源：

1. `DiscoveryProspectBatchSourceContext`
   - `discovery_task_id`、provider、Task 状态；
   - 每家公司对应的 discovery candidate、来源 reference 与候选 website。
2. `RoutingProspectBatchSourceContext`
   - `routing_run_id`、`execution_generation`、`import_session_id`；
   - 每家公司的 `route_id`、effective tier、review status；
   - Route 的 feature snapshot、reason/warning codes；
   - 对应 RawImportRow 与 ImportEntityDecision ID。

Workflow 在入口一次性装载 typed context；后续 preflight、幂等 business key 与 pipeline
来源校验只接收该类型，不在各阶段散落 nullable `discovery_task_id` 分支。Routing Batch
不会伪造 DiscoveryTask，也不会创建虚假的 `discovery_task_id`。

## 5. 选择理由

- 保持 Domain 无 FastAPI、SQLAlchemy、Provider SDK 依赖。
- 复用现有 `ProspectJob`、worker 与深度 pipeline，避免复制 Research/Scoring/Contact/Draft。
- Discovery 与 routing provenance 的事实结构不同，显式 union 比万能 nullable 字段更可审计。
- Route generation 已不可变，旧 Batch 始终读取创建时 generation 的 Route 快照，不自动切换
  到 RoutingRun 的当前 generation。
- 首版只存在两种来源，暂不引入通用 relation/table，控制 D5d1 变更面。

## 6. 未选方案及理由

- 伪造 DiscoveryTask：拒绝，会制造不存在的业务事实并破坏来源审计。
- routing Batch 直接复用 discovery nullable 字段：拒绝，会让业务代码依赖隐式空值约定。
- 新建第二套 routing pipeline/job：拒绝，会复制 lease、retry、Evidence/Resume 与阶段幂等。
- 新增通用 `BatchSource` 表：暂不采用；只有两个来源，当前 typed value context 足够。
- HTTP 内直接跑 Research：拒绝；会破坏快速 202、worker lease 与故障恢复。

## 7. 启动 API

新增 `POST /api/v1/prospect-batches/{batch_id}/start`，成功返回 HTTP 202：

- `batch_id`
- `job_id`
- `status`
- `reused`
- `processing_started=true`

启动前强制校验：Batch 存在、来源为 prospect routing、显式 `confirmation=true`、保存的
RoutingRun/generation 与 context 一致、所有公司仍是 confirmed/overridden effective A、
来源快照完整、最多 5 家、Batch 尚未启动、Provider 可用。重复或并发相同启动只返回同一个
Job；HTTP 不执行 Research。

## 8. Provider 安全边界

- API 创建 Job 前检查 Research 与 Draft Provider 配置；缺 key/model/base URL 时 fail closed，
  返回结构化 503 且不创建 Job。
- worker、Resume 与 Retry 在真正执行外部阶段前再次检查，避免配置在排队后失效。
- `production` 环境禁止 Research 或 Draft 使用 Fake Provider。
- 自动测试只注入 deterministic Fake，不读取、不输出真实 key，不产生付费调用。
- UI 在启动前明确提示可能访问官网和调用已配置 Provider，必须人工确认。

## 9. Workflow 阶段与人工门禁

执行继续复用：Job lease → validating → Research → Evidence gate → Opportunity → Contact
Discovery → Contact ingestion → Decision Maker → Draft Generation。

- 新 claim 从不自动 accepted，停在 `awaiting_evidence_review`。
- pending claim 的 Resume 返回 `EVIDENCE_REVIEW_INCOMPLETE`。
- 全部 claim 审核后 Resume；Research 不重复执行，已完成 Opportunity/Contact/Draft 不重复创建。
- Evidence 不足进入 needs review，不创建 Draft。
- 无联系人不创建虚构 Contact/Decision Maker/Draft。
- 单公司失败不终止其余公司；可重试技术错误由现有 Retry 恢复。
- Draft 状态保持 `generated`，不自动批准；Outreach `sent_version` 为空，Outcome 为 0。

## 10. 前端流程

RoutingRun 的 Batch 区域新增：

- “来源：销售路由”与 execution generation；
- “Batch 已创建 / 深度处理已启动 / 等待证据审核 / 草稿已生成 / 邮件未发送”状态；
- 显式“启动深度处理”按钮和确认框；
- 每家公司阶段、错误、Evidence Review、Resume、Retry 与工作台入口；
- `batch_id`/`job_id` 写入 URL，刷新后读取 Batch、companies 与 execution 恢复状态；
- 复用持久化 sender profile；未配置时提示，但不虚构发件人。

中英文文案均已添加，没有重构完整工作台。

## 11. Smoke 结果

真实 PostgreSQL、Fake/deterministic Provider 的五家公司 smoke 结果：

| 公司场景 | 首次执行 | 人工/重试动作 | 最终结果 |
| --- | --- | --- | --- |
| 新 claim | `awaiting_evidence_review`，无 Opportunity | 人工 accept 后 Resume | completed + generated Draft |
| Evidence 不足 | needs_review，无 Draft | 无自动放行 | 保持人工复核 |
| 无联系人 | `CONTACT_NOT_FOUND`，无虚构联系人/Draft | 无自动补造 | 保持人工复核 |
| 正常完成 | completed | 无 | generated Draft |
| 可重试技术错误 | 首次 `RESEARCH_FAILED` | Retry | completed + generated Draft |

最终统计：3 completed、2 needs_review、0 failed；3 个 Draft 均为 `generated`，3 个 Outreach
均未发送，Outcome 记录为 0。Claim company 的 Research 只执行 1 次；Retry company 执行
2 次。没有重复实体、没有自动确认 Evidence。

## 12. PostgreSQL 与 Worker 测试

| 门禁 | 结果 |
| --- | --- |
| D5d1 PostgreSQL 文件 | 5 passed |
| D5a1/D5b1/D5c/Discovery/ProspectBatch 定向回归（含 D5d1） | 62 passed in 8.51s |
| 并发启动 | 两个请求同一 job_id，reused 为 false/true，各 1 个 Job |
| Worker | HTTP 快速返回且 Research 调用数为 0；随后 worker 正常领取执行 |
| Evidence/Resume | pending claim 阻断；审核后 Resume；Research 不重复 |
| Retry/lease/stale recovery | 既有 PostgreSQL 与 Domain 回归通过 |
| Ruff | `ruff check .` passed |
| mypy | `mypy app tests --strict`，386 source files passed |
| Frontend lint | 0 errors；5 个既有 candidate-cards 未使用变量 warning |
| Frontend build/TypeScript | Next.js production build passed |
| Playwright | 1 passed in 5.3s |
| Alembic | 单一 head `d5c1f2e3a4b6`；fresh test DB `alembic check` passed |

本轮没有 Migration，因此不执行 D5d1 upgrade/downgrade/upgrade。集成 fixture 会重建真实
PostgreSQL test DB 并执行 `upgrade head`。默认本地开发库曾在 D5c migration 修订前已被
stamp 为同一 revision，直接对该旧库运行 `alembic check` 会报告 generation 列/index 差异；
未自动删除或重建用户本地库。fresh test DB 与新部署数据库不存在该问题。

## 13. 兼容性

- 旧 manual_csv Discovery Batch 仍通过原 batch-process 端点创建 Batch + Job。
- discovery Batch 调用新的 routing start 端点返回 409，不改变旧链路。
- D5a1 CSV intake、D5b1 resolution、D5c routing generation/history 定向回归通过。
- D5c 的 `routing_selection_hash` 继续包含 run、generation 与排序 company IDs。
- 不修改历史 Migration，不新增 Alembic head，不删除 `Contact.company_id`，不处理
  CompanyContact 双轨债务。

## 14. 安全检查

- 自动测试和 smoke 未使用真实 LLM、真实联系人 Provider 或付费外部服务。
- 未输出 API key、Token、Prompt 全文或真实联系人邮箱。
- Research claim 必须人工审核；Draft 必须人工审核。
- 未创建发送 API、发送记录或 Follow-up。
- Fake Provider 在 production fail closed。
- 单公司异常仅保存结构化错误摘要，不中断其它公司。

## 15. 新增技术债

1. `ProspectBatchSourceContext` 只支持 discovery/routing 两种来源。
2. Routing source context 在执行时由不可变 Route generation 与原始导入审计记录装载，
   尚未独立持久化一份 BatchSource relation/value snapshot。
3. 前端在现有 Bulk Import 区域内展示 Batch 执行，不是独立批次工作台。
4. PostgreSQL worker 仍为单并发轮询。
5. 本地旧开发库若在 D5c migration 修订前已 stamp，需要由操作者决定备份后重建或迁移。

## 16. 每项债务保留理由

1. 当前只有两个来源，union 清晰且无 schema 成本。
2. Route generation 已保存关键 feature/reason 快照，Raw/Decision 有完整数据库追溯；D5d1
   无需新增表或 Migration。
3. 当前目标是闭合 A 类入口，不是重构完整工作台。
4. 最多 5 家、顺序处理的 MVP 负载不需要 Celery 或新队列。
5. 自动重建默认库可能删除用户本地 D5c 数据，不应在功能任务中静默执行。

## 17. 债务偿还条件

- 出现第三种 Batch source，或来源需要独立生命周期/查询时，评估 BatchSource relation/value
  object 与持久化 snapshot。
- Batch 数量或并发用户使单 worker 延迟不可接受时，再增加受控并发或任务系统。
- 用户验证证明需要跨批次运营视图时，再设计独立 Batch 工作台。
- 本地旧库含需保留的 D5c 数据时，先备份并编写一次性 schema repair；无数据时重建更安全。

## 18. 未完成事项

- D5d1 PR 尚未合并，等待 GitHub checks 与 review。
- 未做真实 Provider smoke；本轮安全要求禁止自动测试产生付费请求。
- 本地旧开发数据库未自动重建，需操作者根据是否保留数据决定。
- 未实现 Umail、Suppression、发送、Follow-up、邮箱验证与 Calibration。

## 19. D5d2 Umail 建议（未实施）

D5d2 只针对已人工确认的 B 类 Route：定义可审计导出任务、固定字段 contract、导出前
Suppression/合规校验，以及导出结果的状态展示。不要复用 D5d1 `ProspectJob` 执行深度
Research；不要把导出等同于发送；不要在 D5d2 自动导入发送结果或实现 Follow-up。
