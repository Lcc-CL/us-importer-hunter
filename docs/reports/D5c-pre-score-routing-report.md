# D5c 确定性 Pre-Score 与销售路由实施报告

## 1. 实现结论

D5c 已完成以下闭环：完成实体归并的 `ImportSession` → 从已持久化事实聚合特征 →
确定性 Pre-Score → A/B/C/D 推荐路由或 blocked → 人工确认、覆盖或排除 → 从已确认的
有效 A 类中选择最多 5 家 → 只创建现有 `ProspectBatch`。

本轮没有创建 `Opportunity`、Research、Draft、ProspectJob 或 Umail 数据，没有自动启动
深度处理，没有调用 LLM、付费 API 或外部 Provider，也没有发送邮件。

## 2. Git / PR 状态

- D5b1 PR #6 已于本轮开始时确认并使用 Squash Merge 合并；merge commit 为
  `0d762cbd49d5cbce757892a8272b142c4230aef9`。
- D5c 分支：`feat/prospect-pre-score-routing`，从上述最新 `main` 创建。
- PR #4 `feat/real-prospect-calibration-mvp` 仍为 OPEN；本轮没有修改、合并或
  cherry-pick 该 PR。
- D5c 目标 commit：`feat(routing): add deterministic prospect pre-score and routing`。
- D5c PR 在本报告与实现 commit 推送后创建，标题为
  `feat(routing): add auditable A/B/C/D prospect routing`；按要求本轮不合并该 PR。
- 未创建 release tag。

## 3. 数据模型和 Migration

新增 Migration：`d5c1f2e3a4b6_add_prospect_pre_score_routing.py`，后继 D5b1
`d5b1e2f3a4b5`，保持单一 Alembic head。

### ProspectRoutingRun

`prospect_routing_runs` 保存一次版本化路由配置及其执行结果，包括：

- `import_session_id`、`rules_version`、`configuration_hash`；
- `entity_state_hash`、`execution_generation`，用于同配置下检测实体审核或联系人投影变化；
- `criteria_json`、`weights_snapshot_json`；
- pending / running / completed / partial_completed / failed 状态；
- total、routed、blocked、A/B/C/D 统计；
- started / completed / error / created / updated 审计字段。

数据库唯一约束为
`(import_session_id, rules_version, configuration_hash)`。同一条件和相同实体状态复用已有
Run；实体状态改变时保留同一 Run ID、增加 `execution_generation`、清除旧 Route 后重新计算。

### ProspectRoute

`prospect_routes` 每个 Run、每家公司最多一条，保存：

- `pre_score`、recommended/effective tier；
- 完整 `feature_snapshot_json`；
- `reason_codes`、`warning_codes`；
- suggested / confirmed / overridden / blocked 审核状态；
- 人工理由、审核人、审核时间；
- 联系人数、可用联系人/邮箱、首选角色快照。

blocked Route 在 Domain 与数据库约束中均禁止拥有正式 tier。Pre-Score 和路由判断没有写入
Company，Canonical Company facts 未被修改。

### 复用 ImportProcessingJob

`import_processing_jobs` 增加 `job_type = entity_resolution | prospect_routing` 和单个 nullable
`routing_run_id`。数据库约束保证 entity-resolution job 不引用 RoutingRun、routing job 必须
引用 RoutingRun。

### 扩展 ProspectBatch 来源

`prospect_batches` 现在允许且只允许一种来源：原有 `discovery_task_id`，或新增
`routing_run_id + routing_selection_hash`。路由选择 hash 包含 Run、执行代次和排序后的公司
ID，重复选择明确幂等。D5c 创建 Batch 时不会创建 `prospect_batch_jobs`。

Migration 已在 Docker PostgreSQL 完成 upgrade → downgrade 到 D5b1 → upgrade，并通过
`alembic check`。Downgrade 在存在路由来源 Batch 或 routing job 时 fail closed，避免静默丢失
业务数据。

## 4. 特征和评分公式

规则版本：`d5c-deterministic-routing-v1`。内部权重固定并随 Run 保存，用户不能修改。

| 维度 | 最大分 | 第一版公式 |
| --- | ---: | --- |
| 产品 / HS 匹配 | 30 | 仅配置一种时占满 30；两者都配置时产品 60%、HS 40% |
| 最近进口 | 20 | ≤90 天 100%；≤180 天 75%；≤365 天 50%；≤730 天 25%；更久或缺失 0 |
| 进口频率和持续性 | 15 | `0.6 × min(Raw 行数/12,1) + 0.4 × min(活跃月份/6,1)` |
| 来源国 | 10 | 有偏好时匹配偏好；未配置时匹配中国/亚洲国家集合 |
| POL / POD | 10 | 对已配置的 POL、POD 维度取平均匹配率；均未配置时为 0 |
| 联系人覆盖与职位 | 10 | 40% 联系人覆盖（2 人封顶）+ 60% 首选角色存在性 |
| 数据完整度 | 5 | 产品/HS、日期、来源国、港口、公司资料、联系人六项等权 |

联系人首选角色为 owner_founder、executive、procurement、supply_chain、logistics、
operations、import_export。弱 `possible_intermediary` 单信号只产生 warning 并扣 5 分；明确
中介类型或两个及以上独立中介类别才是强排除。

`feature_snapshot_json` 保存每个维度的 0–100 特征分、实际加权分、观察到的产品/HS/国家/
港口、行数、活跃月份、联系人统计、完整度 flags、中介信号与 penalty、冲突状态以及最终
计算总分。每个维度和路由结论均生成 reason code，缺失或风险生成 warning code。

## 5. A/B/C/D 规则

- A：`score >= 75`，至少一个 active 且有可用 channel 的联系人，并存在至少一个首选角色；
  无 unresolved company conflict，无强排除。
- B：`score >= 50`，至少一个可用 email 联系人；无强排除。B 仅代表候选，不代表可发送。
- C：`score >= 30`，包括分数足够但联系人或职位条件不足、无法进入 A/B 的公司。
- D：`score < 30`，或存在明确产品/HS 不匹配，或命中强中介排除，或人工 exclude。
- blocked：存在待审核的公司身份冲突；仍保存特征快照，但无正式 tier，不计入 A/B/C/D。

人工 review 支持 confirm、override、exclude。完全相同的重复提交幂等；tier、理由或审核人
不同的后续提交返回结构化 409，避免覆盖既有人工判断。

## 6. Worker 技术选择及原因

最终选择：复用 D5b1 `ImportProcessingJob` 和现有 Import Worker，通过 `job_type` 分发到
entity resolution 或 prospect routing workflow。

选择理由：

1. 两类任务都需要相同的 PostgreSQL lease、heartbeat、retry、stale recovery 和
   `FOR UPDATE SKIP LOCKED` 语义。
2. 仅增加一个受约束的 nullable `routing_run_id`，没有引入一组稀疏 subject 外键。
3. 保持单 worker、单部署单元和现有运行手册，符合 MVP 范围。

未选方案：没有新增 ProspectRoutingJob 表，也没有引入 Celery、Kafka、RabbitMQ 或另一套
队列。单独表会立即复制恢复协议和测试；通用 `subject_type/subject_id` 又会失去数据库 FK。

Lease、retry、heartbeat、stale recovery 均有真实 PostgreSQL 定向测试。路由每处理 100 家
公司 heartbeat 一次；结果在最后一个事务整体替换，失败不会留下半批 Route。

## 7. API

- `POST /api/v1/import-sessions/{session_id}/routing-runs`：结构化 422 校验目标产品/HS，
  返回 202、Run/Job ID、reused/recalculated。
- `GET /api/v1/prospect-routing-runs/{routing_run_id}`：状态、进度、A/B/C/D/blocked、规则、
  条件、权重、Job retry/heartbeat/error。
- `GET /api/v1/prospect-routing-runs/{routing_run_id}/routes`：tier、review status、分数区间、
  has contact、role、分页过滤。
- `POST /api/v1/prospect-routes/{route_id}/review`：confirm / override / exclude；冲突 409。
- `POST /api/v1/prospect-routing-runs/{routing_run_id}/prospect-batches`：1–5 家，只接受已
  confirmed/overridden 的 effective A，重复选择返回同一 Batch，`processing_started=false`。

Route 保持薄 HTTP adapter；校验、幂等、路由审核和 Batch 前置条件均在 schema、Domain 或
Workflow 中。

## 8. 前端流程

Import Session 页面新增最小“销售路由”阶段：

1. 输入产品关键词、HS Code、来源国、POL/POD、Campaign；
2. 创建并轮询 RoutingRun，显示规则版本、进度和 A/B/C/D/blocked；
3. 显示公司、Pre-Score、推荐/生效 tier、reason、warning、联系人和首选角色；
4. 支持确认推荐、修改 tier、人工排除和审核理由；
5. 从已审核 A 类勾选最多 5 家创建 ProspectBatch；
6. 创建后明确显示“已创建深度处理批次，尚未启动 Research 或邮件生成。”

`routing_run_id` 写入 URL，刷新后恢复 Run、统计、Route 和审核结果。中英文文案均已加入，
没有新增 Umail 页面，也没有重构现有前端结构。

## 9. 性能结果

真实 Docker PostgreSQL、合成数据：500 Company、5,000 Contact/CompanyContact、10,000
RawImportRow；Routing 计时从提交 Run 到后台 worker 完成，不包含之前的 CSV 导入和实体归并。

| 指标 | 结果 | 目标 |
| --- | ---: | ---: |
| 总耗时 | 3.961 秒 | < 60 秒 |
| Python 峰值内存 | 62,695,327 bytes（约 59.8 MiB） | < 256 MiB |
| SQL statements | 77 | < 100 |
| 明显 N+1 | 否 | 否 |
| ProspectRoute | 500 | 500 |

初次测量为 117 SQL。根因是 ORM `selectin` 在 5,000 Contacts 上分别分块加载 channels 和
sources，尽管路由不需要完整 Contact Aggregate。改为 Repository 内一次显式联系人/可用
channel 聚合投影后降至 77 SQL；Repository 仍返回 Domain snapshot，没有暴露 ORM Model。

## 10. 冲突型性能结果

性能数据中 50 家公司（10%）被人工构造成 `review_required + pending`：

- RoutingRun 为 `partial_completed`；
- A=450、B=0、C=0、D=0、blocked=50；
- 其他 450 家继续完成评分和路由；
- blocked Route 仍保存特征与原因，但 tier 为 null；
- 未创建 Opportunity、Research、Outreach、ProspectBatch；
- 冲突没有导致 worker 失败、超时或全局阻塞。

## 11. 测试门禁

| 门禁 | 结果 |
| --- | --- |
| D5c scorer / Domain / API / Migration / architecture boundaries | 22 passed |
| 500/5,000/10,000 PostgreSQL 性能 | 1 passed |
| D5a1 / D5b1 / Discovery / Company / Contact / ProspectBatch 兼容 | 33 passed |
| Ruff | `All checks passed!` |
| strict mypy | `Success: no issues found in 385 source files` |
| Alembic heads | 单一 `d5c1f2e3a4b6 (head)` |
| Migration 往返 | upgrade / downgrade / upgrade 通过 |
| alembic check | `No new upgrade operations detected.` |
| Frontend TypeScript | `npx tsc --noEmit` 通过 |
| Frontend ESLint | 0 error；5 个既有 candidate-cards warning |
| Frontend production build | 通过 |
| Playwright D5c | 1 passed；上传→归并→刷新→路由→刷新→确认→Batch |

按任务要求没有运行 900+ 全仓 pytest；运行范围只覆盖 D5c、Migration、旧主链兼容和浏览器
闭环。

## 12. 兼容与安全

- 旧 D5a1 CSV、D5b1 entity resolution、DiscoveryTask 来源 ProspectBatch 均保留。
- `Contact.company_id` 未删除；D5b1 `CompanyContact` 双轨债务未偿还。
- `CompanyResolutionProfile` 仅作为当前归并投影使用，没有描述为历史事实表。
- 没有读取或输出真实 `.env` 值，没有记录完整联系人邮箱，没有提交真实网易 CSV。
- 性能和 E2E 使用合成数据与 Fake Provider；没有调用真实 LLM 或外部 Provider。
- 没有自动发送邮件，也没有把创建 ProspectBatch 表述为已经开发或触达。

## 13. 新增技术债

1. `ImportProcessingJob` 现在承载两种 job type，并有一个受约束的 nullable
   `routing_run_id`。
2. `ProspectBatch` 暂时支持 discovery/routing 两种来源字段，以保持 D3 与 D5c 兼容。
3. 每次重复提交都重新聚合 source snapshot 并计算 `entity_state_hash`，成本随 Session 数据量
   线性增长。
4. 路由规则是固定的关键词、前缀 HS 和阈值策略，尚未做真实销售结果 Calibration。
5. 路由来源 Batch 在 D5c 中只能创建，现有深度处理 workflow 对它明确 fail closed。
6. Import Worker 仍是单并发轮询；entity resolution 与 routing 共用一个 worker pool。

## 14. 每项债务保留理由

1. 两类 import job 的执行可靠性语义完全相同，复制表和 coordinator 会增加更高风险。
2. 改写历史 ProspectBatch 来源模型会扩大 D5c diff，并威胁已运行的 D3/D4 链路。
3. 全量 hash 在 500/10,000 场景仍远低于 SLA，当前优先保证审核变化一定触发重算。
4. 本轮目标就是可审计确定性 Pre-Score；LLM/ML、自动学习和 Calibration 明确排除。
5. 自动 Research 明确禁止；fail closed 防止用户误以为 Batch 创建等于已处理。
6. 当前规模 3.961 秒完成，尚无证据需要并发队列或独立 worker pool。

## 15. 债务偿还条件

1. 出现第三种以上 import job subject，或 nullable subject 字段继续增加时，评估通用 job
   subject 表或按 bounded context 拆分 job 表。
2. discovery/routing 之外出现更多 Batch 来源，或两类 Batch 生命周期开始显著分叉时，抽取
   显式 BatchSource value object / relation。
3. 单个 Session 达到十万级 Raw 行、重复提交 p95 超过产品 SLA，或 hash 成为数据库热点时，
   引入 resolution revision/version，而不是继续扫描全部 snapshot。
4. 收集到足够真实销售人工判断和结果后，再以独立 rules version 做 Calibration；不得静默
   修改 D5c 权重。
5. 产品批准“显式启动 A 类深度处理”后，以单独用户动作创建 ProspectJob，并验证路由来源
   证据边界。
6. Worker 排队延迟、lease 冲突或吞吐 SLA 被真实数据证明不足时，再拆分 worker pool 或增加
   受控并发。

## 16. 未完成事项

以下均为明确的后续阶段，不是 D5c 阻塞：

- 路由来源 Batch 的显式 Research/Opportunity/Draft 启动动作；
- Umail CSV 导出、Suppression、Umail 结果回传；
- 邮箱验证、外部联系人 Provider；
- 自动发送、自动 Follow-up；
- LLM/ML 评分、自动学习权重和 Calibration 扩展；
- PR #4 Calibration 内容；
- 多 worker pool、Celery、Kafka、RabbitMQ。

## 17. D5d 建议（本轮不实施）

D5d 应只实现“已确认 A 类 ProspectBatch 的显式深度处理启动”：用户再次确认后创建现有
ProspectJob，逐家公司复用 Research → 证据人工审核 → Opportunity → 决策人 → Draft，页面
清楚区分 queued、awaiting evidence review 与 completed。验收必须继续保证不自动确认证据、
不自动发送邮件、重复启动幂等，并对 routing source 缺少旧 DiscoveryTask provenance 的情况
设计明确 typed boundary，而不是绕过现有安全检查。
