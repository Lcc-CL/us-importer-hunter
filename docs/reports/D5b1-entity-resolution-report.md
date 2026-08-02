# D5b1 公司与联系人实体归并基础报告

## 1. 实现结论

D5b1 已完成 `ImportSession / RawImportRow → 确定性公司与联系人识别 →
CompanyContact 任职关系 → ImportEntityDecision 审计 → 人工复核 → 刷新恢复`
的后台处理闭环。

相同来源与 external company ID、相同域名、相同标准化名称与地址可稳定复用
Canonical Company；联系人可按全局邮箱或 LinkedIn 身份复用，并可通过不同
CompanyContact 关联多个公司。存在名称、地址或公司类型冲突时不会提前落任职关系，
必须完成人工 merge / keep separate / reject 后才继续关联。

本轮未调用真实 LLM 或外部 Provider，未创建 Pre-Score、Opportunity、Research、
ProspectBatch、Draft、Umail 或邮件发送数据。

## 2. Git / PR 状态

- D5a1 PR #5 已在本轮开始时确认 OPEN、CLEAN、checks SUCCESS，并使用 Squash Merge
  合并。
- D5a1 合并后的 `main`：`6e0440c18d63b8d100646078470d3e2f5daa5b81`，当时与
  `origin/main` 一致。
- D5b1 分支：`feat/import-entity-resolution-foundation`，从上述 main 创建。
- 目标 Commit message：`feat(import): add company and contact entity resolution`。
- 目标 PR 标题：`feat(import): add auditable company and contact resolution`。
- 本报告随 D5b1 feature commit 提交；PR 在该 commit 推送后创建，最终 URL 见
  GitHub PR metadata 与交付回复。
- PR #4 `feat/real-prospect-calibration-mvp` 保持 OPEN；未合并、未修改、未
  cherry-pick。
- 未创建 release tag，D5b1 PR 不在本轮合并。

## 3. 数据模型和 Migration

新增独立 Migration：
`app/database/migrations/versions/d5b1e2f3a4b5_add_import_entity_resolution.py`，
后继 D5a1，保持单一 Alembic head。

新增模型：

- `CompanyExternalIdentity`：`UNIQUE(source, external_id)`，稳定指向一个 Company；
  保存 first/last seen 和审计时间。
- `CompanyResolutionProfile`：确定性匹配使用的内部投影，保存 normalized name、
  domain、address、company type、phone 与来源 Raw 行。
- `CompanyContact`：Company 与 Contact 的任职关系，唯一约束
  `(company_id, contact_id)`，保存职位分类、seniority、部门邮箱标记、first/last
  seen 和来源 Raw 行。
- `ImportEntityDecision`：每个 Session、Raw 行、实体类型唯一；保存候选实体、决定、
  置信度、reason codes、reviewer 和 review 时间。
- `ImportResolution`：Session 级处理状态与统计。
- `ImportProcessingJob`：独立的 import resolution 后台任务，支持 lease、retry、
  heartbeat、stale recovery 与结构化错误。

兼容变更：

- `Contact.company_id` 保留，改为 nullable 和 `ON DELETE SET NULL`。
- Migration 将所有历史单公司 Contact 回填为 CompanyContact。
- `companies.normalized_name` 从唯一索引改为普通索引，以允许人工
  `keep_separate` 保留同名公司。
- Migration 已通过 upgrade → downgrade → upgrade；downgrade 会先从最早的
  CompanyContact 恢复 legacy `Contact.company_id`，存在仍未归属 Contact 时明确拒绝
  降级，防止静默丢失关系。
- `alembic check`：`No new upgrade operations detected`。

## 4. 公司归并规则

规则按以下顺序执行，全程无 LLM：

1. 相同 source + external company ID：1.0 置信度自动复用；人工 merge 后也会写入
   external identity，保证后续文件稳定复用。
2. 相同 normalized domain：通常自动复用；名称低相似、地址冲突、公司类型冲突或
   多候选时进入 `review_required`。
3. 相同 normalized company name + normalized address：自动复用。
4. email domain 与 phone 仅作为辅助信号，不独立自动归并。
5. 仅名称相似：进入 `review_required`。
6. 无足够信号：创建独立 Company；缺少有效公司名则 rejected。
7. 疑似货代、仓库、报关代理只记录 `possible_intermediary` warning，不删除 Raw 数据。

Profile 使用 first-non-empty 投影；冲突不覆盖 Canonical Company，而是保存在
ImportEntityDecision reason codes 中。

## 5. 联系人归并规则

- normalized email 全局匹配：复用 Contact person identity。
- normalized LinkedIn URL 全局匹配：高置信复用。
- normalized name + 同公司 + title：`review_required`；仅姓名不会自动归并。
- 同一邮箱跨公司：复用 Contact，新增或更新不同 CompanyContact，不覆盖旧任职。
- 无已确认公司：允许创建 nullable company_id 的暂存 Contact，不进入后续销售路由。
- 部门邮箱按确定性前缀词库识别，自动生成部门显示名并标记
  `is_department_contact=true`。
- 邮箱域与官网域不一致记录 `email_domain_mismatch` warning，不删除联系人。
- 职位使用确定性词库映射 owner_founder、executive、procurement、supply_chain、
  logistics、operations、import_export、warehouse、sales、general_department、
  irrelevant、unknown；不使用 LLM。
- 人工 merge 会保留新的 Contact source，并补充尚不存在的 email、LinkedIn 或 phone
  channel。

## 6. Job / Worker 技术选择及理由

最终选择：新增最小 `ImportProcessingJob`，复用 Prospect worker 已验证的 lease、retry、
heartbeat、stale recovery 语义和 PostgreSQL `FOR UPDATE SKIP LOCKED` 模式。

选择理由：现有 ProspectJob 强绑定 ProspectBatch 和批次公司阶段，不具备通用
subject_type / subject_id；复用其表会污染 ProspectBatch 业务语义，并引入大量 nullable
外键或分支。

未选方案：

- 未把 ImportSession 字段塞入 ProspectJob。
- 未创建万能 Job 或新的队列框架。
- 未引入 Celery、Kafka、RabbitMQ 或额外依赖。

Worker 每轮各尝试处理一个 import job 和一个 prospect job，避免 import 归并改变既有
ProspectBatch 行为。

## 7. API

- `POST /api/v1/import-sessions/{session_id}/resolve`：HTTP 202；返回 Session、job、
  status 与是否复用已有任务。
- `GET /api/v1/import-sessions/{session_id}/resolution`：返回处理状态、进度、公司/
  联系人创建和复用、待复核、CompanyContact、错误行、失败行、attempt 与 heartbeat。
- `GET /api/v1/import-sessions/{session_id}/entity-decisions`：支持 entity type、review
  status、confidence 范围、page 与 limit。
- `POST /api/v1/import-entity-decisions/{decision_id}/review`：支持 merge、
  keep_separate、reject；同一动作重复提交幂等，不同动作返回冲突。
- Route 只做验证和 schema 映射；业务编排位于 Workflow。
- 错误继续由统一 handler 返回 `code / message / request_id`。

## 8. 前端流程

现有 Import Session 页面新增最小 D5b1 区域：

1. 上传网易 CSV 并查看 Raw Intake 结果。
2. 点击“开始实体归并”，创建后台 job。
3. 轮询并展示 pending / running / completed / partial_failed / failed。
4. 展示公司新建/复用/待复核、联系人新建/复用、任职关系和失败行统计。
5. 展示待复核决定、候选实体、置信度和 reason codes。
6. 执行合并、保持分离或拒绝。
7. URL 保留 `import_session_id`，刷新后恢复 Session、Resolution 和待复核列表。

页面固定提示：“实体归并完成不代表已完成机会评分、开发或邮件发送。”
未重构其他前端，也未新增 Pre-Score 或 Umail 页面。

## 9. 性能结果

环境：本地 macOS、Python 3.12、Docker PostgreSQL 16、FastAPI ASGI client、合成 CSV；
不包含真实网易或联系人数据。

场景：500 家公司、5,000 个唯一联系人、10,000 条 accepted RawImportRow；每个联系人
跨两条非重复 Raw 行出现一次创建和一次复用。

| 指标 | 结果 |
|---|---:|
| CSV 大小 | 1,276,269 bytes |
| 实体归并耗时 | 33.153 秒 |
| tracemalloc 峰值内存 | 13,903,394 bytes（约 13.26 MiB） |
| SQL statements | 962 |
| Company 新建 / 复用 | 500 / 9,500 |
| Contact 新建 / 复用 | 5,000 / 5,000 |
| CompanyContact 新建 | 5,000 |
| ImportEntityDecision | 20,000 |
| review_required | 0 |
| failed rows | 0 |
| Opportunity / Research / Outreach | 0 / 0 / 0 |

结果满足小于 120 秒、小于 256 MiB 的目标。10,000 行共 962 条 SQL，主要热点为 40 个
250-row batch 的 Raw 行读取、分批 INSERT/UPDATE、Resolution/Job heartbeat 和初始候选
索引加载；没有每行 SELECT，未观察到明显 N+1。

## 10. 测试结果

| 门禁 | 结果 |
|---|---|
| Migration + D5b1 PostgreSQL API | 5 passed in 6.38s |
| Company/Contact/Discovery/ProspectBatch 定向兼容 | 75 passed in 10.78s |
| 人工 merge external ID / Contact channel 补充 | 3 passed in 1.85s |
| 10,000-row PostgreSQL performance | 1 passed in 34.83s；核心计时 33.153s |
| Alembic | upgrade/downgrade/upgrade 通过；check 无漂移 |
| Ruff | `ruff check .` 通过 |
| mypy | `mypy app tests --strict` 通过，370 source files |
| Frontend TypeScript | `npx tsc --noEmit` 通过 |
| Frontend lint | 0 error；5 个既有 candidate-cards warning |
| Frontend production build | 通过；首次沙箱内失败原因为 Turbopack 禁止绑定端口，非沙箱重跑通过 |
| Playwright | D5b1 upload → background resolve → refresh → merge：1 passed in 4.7s |
| E2E TypeScript | 使用仓库现有 TypeScript compiler 通过 |

按本轮要求未重复运行 900+ 全仓测试；只运行 D5b1、Migration、旧主链兼容和前端核心
闭环的定向门禁。

## 11. 安全检查

- 未读取、输出或提交真实 `.env` 值。
- 未提交真实网易 CSV；所有 CSV 均为测试内合成数据。
- Worker 错误日志只记录 job/session ID 和异常类型，不记录完整联系人邮箱。
- Decision API/报告不返回 Raw payload，只返回 Raw row ID、行号、候选标签和 reason codes。
- 未调用真实 LLM、ImportYeti、LinkedIn、邮箱验证或其他外部 Provider。
- 未创建发送任务，未发送邮件。
- 隔离 E2E 数据库 `importer_hunter_e2e` 已在测试后删除。

## 12. 兼容策略

- 保留 legacy `Contact.company_id`，历史数据可继续通过旧 Contact API、Decision Maker、
  MVP analyze 和 ProspectBatch 读取。
- 新导入流程以 CompanyContact 为任职关系真相；Contact repository 查询公司联系人时同时
  读取 legacy company_id 与 CompanyContact。
- Company 删除对 legacy Contact 使用 SET NULL，对该 Company 的 CompanyContact 使用
  CASCADE；共享 Contact 及其他公司的任职关系保留。
- Decision Maker/scorer/workflow 对 nullable company_id 做显式校验，无公司归属 Contact
  不进入旧销售路由。
- Company normalized name 不再全局唯一；旧 name lookup 使用 created_at 排序并确定性返回
  最早记录，避免 `scalar_one` 错误。
- Migration、旧 Company/Contact repository、Discovery API 和 ProspectBatch API 已在真实
  PostgreSQL 上定向回归。

## 13. 新增技术债

1. `Contact.company_id` 与 CompanyContact 双轨存在。
2. Company normalized name 不再是数据库唯一身份，只是候选信号。
3. CompanyResolutionProfile 是当前投影，不保存逐字段历史版本。
4. 自动 Contact merge 主要通过 Decision + CompanyContact 保留新来源；只有人工 merge
   会把新的缺失 channel 投影回 Contact。
5. 待复核 API 当前只展示一个最佳候选，不展示候选排序列表。
6. `reviewed_by` 仍是调用方提供的本地字符串，没有认证用户绑定。
7. Worker 仍是单进程、每类任务一次处理一个 job。

## 14. 每项债务保留理由

1. 立即删除 company_id 会扩大旧 Contact、Outreach、Decision Maker 和 Migration 风险。
2. `keep_separate` 必须允许现实中同名但不同实体的公司共存。
3. D5b1 只需要可审计决定和 first/last seen；字段级 SCD 历史超出 MVP。
4. 自动匹配高频路径避免每行加载/保存 Contact 导致 N+1；Raw 行、Decision 和任职关系仍
   保留完整审计链。
5. 多候选 UI 会扩大 API 与产品交互；当前规则只需要人工接受最佳候选或保持分离。
6. 项目当前没有 auth/multi-tenancy，伪造 User 表不符合 MVP 边界。
7. 10,000 行已满足 120 秒目标，不需要提前引入 Celery 或多进程协调。

## 15. 债务偿还条件

1. 所有旧 Contact/Decision Maker/Outreach 查询完成 CompanyContact 迁移并完成数据回填
   验证后，新增 Migration 删除 legacy company_id。
2. 有真实误合并/同名公司数据后，引入独立 canonical identity/alias 管理策略，而不是恢复
   简单唯一索引。
3. D5c 若需要可解释字段更新或冲突解决，再增加 append-only profile observation/history。
4. 真实 CSV 证明同一 LinkedIn/邮箱会持续补充新渠道，且需要在 Contact 全局层展示时，
   增加批量 Contact fact merge，保持 SQL 非 N+1。
5. 真实审核者需要比较多个候选时，再增加候选表和排序 UI。
6. Auth/Identity 进入 MVP 后，将 reviewed_by 替换为受信 user ID。
7. 单 worker 接近 SLA 或出现队列争用后，再评估并发和独立 worker pool。

## 16. 未完成事项

以下均为明确排除或后续阶段，不是 D5b1 阻塞：

- Pre-Score 与 A/B/C/D 路由。
- ProspectBatch 自动创建。
- Research、Opportunity、Decision Maker 销售路由与 Email Draft 自动触发。
- 网易发送导出、发送结果导入、Suppression 和 Umail 页面。
- LLM/ML entity matching、真实 Provider、邮箱验证和邮件发送。
- Calibration PR #4 的任何合并或扩展。

D5b1 当前无已知 P0 阻塞。

## 17. D5c 建议（本轮不实施）

D5c 应只推进“可审计 Pre-Score 与人工路由输入”：消费已完成且无待复核决定的
ImportResolution，按可解释规则生成独立判断记录，再由用户决定哪些 Company 进入最多
5 家的 ProspectBatch。验收应继续保证 Company 保存事实、判断不写回 Company、无自动
Research/发送，并以本轮 500/5,000/10,000 性能基线作为回归门槛。
