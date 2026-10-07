# D5d2b Umail 离线结果回传、Engagement 与自动 Suppression 报告

日期：2026-08-03（America/Los_Angeles）

分支：`feat/umail-result-feedback-loop`

目标：Umail 离线发送结果 CSV → 可审计 Result Import → 确定性 ExportRow 关联 → append-only Engagement → 必要 Suppression → 前端结果与统计。

## 1. PR #9 修复与合并状态

- D5d2a PR #9 已完成仓库卫生与 CSV V1 合同修复后 Squash Merge。
- 修复 commit：`0f60b27a31817076e96c16f6239a042475af38a1`。
- `main` merge commit：`cca72586d38e70ae93b896173dede1e5d9c9e25e`。
- GitHub 状态：PR #9 `MERGED`，合并时间 `2026-08-04T03:04:46Z`。
- D5d2b 从该最新 `main` 创建；开始时本地 `main`、`origin/main` 与 feature branch 基线一致。
- PR #4 Calibration 仍为 `OPEN`，本轮未修改、未合并。
- 未创建 release tag。

## 2. 仓库卫生审计

- PR #9 中截图出现的 `/private/tmp/.../smoke.py` 从未进入 Git 跟踪；D5d2b 也未跟踪该文件。
- `git ls-files` 未发现 `.dump`、Playwright 报告、测试结果目录、临时 cache/tmp 目录或本地数据库备份。
- 仓库中 `/private/tmp` 仅出现在仓库卫生测试的禁止规则内，不是运行时绝对路径依赖。
- D5d2b 新增文件只包括正式源码、Migration、测试、前端和本报告。
- `git diff --check` 通过，无空白错误。
- legacy 开发数据库和既有 dump 未删除、未迁移、未写入；本轮只升级当前新开发库和隔离测试库。

## 3. D5d2b 实现结论

D5d2b 已实现完整的离线反馈闭环：用户上传可映射 CSV，系统保存文件 hash、Mapping 快照和每一原始行；按四级确定性规则关联不可变 Umail 导出快照；先展示 matched/unmatched/ambiguous/invalid/duplicate 预览；只有明确确认 Apply 后才追加 Engagement，并为 hard bounce、unsubscribe、complaint 创建必要的 email Suppression。前端支持 URL 恢复、过滤、行级关联来源和多维统计。系统不调用 Umail API、不调用 LLM/Provider、不发送邮件。

## 4. 技术选择及理由

采用独立 `umail_feedback` bounded context，核心选择如下：

1. 两阶段 `upload/preview → explicit apply`：外部结果可能存在字段差异或关联歧义，必须先人工审核。
2. append-only `ContactEngagementEvent`：发送结果是发生过的事实，同一联系人可跨 Campaign、多次触达，不能覆盖历史。
3. 不可变 ExportRow 快照关联：发送结果必须指向当时导出的公司、联系人、邮箱、Campaign 和 Route，不能读取联系人当前值重写历史。
4. 确定性、分级关联：优先强标识，只在唯一时采用弱一级关联；不按姓名或公司名猜测。
5. 事件驱动 Suppression：只有永久失败或明确拒收类事件自动抑制，临时/未知 bounce 保留人工判断空间。
6. 同步 HTTP、20,000 行上限：10,000 行样本在目标预算内，MVP 暂不引入新队列或对象存储。

## 5. 未选方案及理由

- 未修改 `UmailExportRow`：导出快照属于不可变审计记录，结果生命周期独立。
- 未使用 `Outreach.mark_sent`：CSV 下载和外部 Umail 发送结果不能冒充本系统发送。
- 未覆盖 Contact 状态：Engagement 是历史事件，不是联系人主数据状态。
- 未写 Draft/Outcome：发送结果不属于草稿审批状态，也不应在旧 Outcome 模型中丢失 Campaign/ExportRow 追溯。
- 未采用姓名、公司名或模糊匹配：误关联会污染 Engagement、Suppression 和后续校准数据。
- 未上传后自动 Apply：ambiguous/unmatched/invalid 必须先可见，用户必须明确确认。
- 未接 Umail API、异步 worker 或对象存储：当前目标是低依赖验证闭环，文件格式尚未稳定到值得外部集成。

## 6. 数据模型与 Migration

新增 Alembic revision：`d5d2b1c2d3e4`，父 revision 为 `d5d2a1b2c3d4`；未修改任何 D5a–D5d2a 历史 Migration。

开发期间初版 revision 已在新开发库试跑，随后 Preview 增加最终投影计数字段。重跑前只读确认三张 D5d2b 新表均为 0 行，再仅对尚未合并的 D5d2b revision 执行 `downgrade d5d2a → upgrade head`；既有业务表、legacy 数据库和 dump 均未触碰。最终两个投影列均存在，schema drift 为 0。

### UmailResultImport / `umail_result_imports`

- 保存文件名、SHA-256、Mapping version、Mapping 快照、状态与创建/应用审计。
- 保存 matched/unmatched/ambiguous/invalid/duplicate 计数。
- 保存 `projected_event_count` 和 `projected_suppression_count`，使刷新后仍能准确展示 Apply 影响预览。
- 保存实际 `applied_event_count` 和 `suppression_created_count`。
- `(file_sha256, mapping_version)` 唯一，保证同一合同下同文件幂等。

### UmailResultRow / `umail_result_rows`

- 保存原始受控 JSON、标准化字段、事件、时间、bounce/message 元数据、关联状态、关联来源和错误代码。
- `UNIQUE(result_import_id, row_number)`。
- `UNIQUE(result_import_id, row_fingerprint)`；持久化 fingerprint 包含语义 hash 和行号，使重复源行仍可保存并标为 duplicate。
- `matched_export_row_id` 外键指向不可变 `umail_export_rows`。

### ContactEngagementEvent / `contact_engagement_events`

- 保存 Import/ResultRow/ExportBatch/ExportRow/Company/Contact 全链路 ID。
- 保存 event、occurred_at、Campaign、provider、metadata 和创建时间。
- `UNIQUE(event_fingerprint)`，事件只追加、不更新。
- 关键查询索引覆盖 Import、Contact、Company、Campaign/EventType 与时间。

## 7. Result Contract

内部合同：`umail-result-import-contract-v1`。

默认逻辑字段：

1. `export_batch_id`
2. `export_row_id`
3. `email`
4. `campaign`
5. `event_type`
6. `occurred_at`
7. `bounce_type`
8. `message_id`

上传允许提供“逻辑字段 → CSV 列名”JSON Mapping；系统保存完整 Mapping 快照。CSV 只接受 UTF-8 或 UTF-8 BOM，最大 20 MB / 20,000 行。时间统一转为 UTC；邮箱 casefold 标准化；未知事件不猜测，标为 `unsupported_event`。`bounce + hard/soft/unknown` 通过版本内固定别名表确定性归一。

## 8. 匹配优先级

严格顺序：

1. `export_row_id` 精确匹配，并校验可选 batch/email/campaign 一致性；
2. `export_batch_id + normalized_email`，仅唯一时匹配；
3. `campaign + normalized_email`，仅唯一时匹配；
4. `normalized_email` 在结果时间前 180 天至允许 1 天时钟偏差窗口内唯一匹配；
5. 无候选为 `unmatched`，多个候选为 `ambiguous`。

严禁姓名匹配、公司名匹配、模糊合并或自动采用 ambiguous。Repository 一次批量加载 ExportRow/Batch 快照，不逐行查询。

## 9. Engagement 事件

支持全部 10 类事件：

- `sent`
- `delivered`
- `hard_bounced`
- `soft_bounced`
- `bounce_unknown`
- `unsubscribed`
- `complained`
- `replied`
- `opened`
- `clicked`

事件 fingerprint 基于 ExportBatch、ExportRow、事件类型、发生时间、Campaign、provider 和 message ID；不含本次 Import/ResultRow ID，因此同一事件跨文件重复导入仍幂等。`bounce_unknown` metadata 写入 `needs_review=true`。Preview 阶段不创建任何事件；只有 Apply 才批量追加。

## 10. Suppression 自动化

自动创建 email Suppression：

- `hard_bounced` → `reason=bounced`
- `unsubscribed` → `reason=unsubscribed`
- `complained` → `reason=complained`

不自动 Suppression：sent、delivered、soft bounce、unknown bounce、replied、opened、clicked。

规则验证：

- 已有 active email Suppression 不重复创建。
- 同一 Apply 内同一邮箱最多创建一条 active Suppression。
- inactive 历史 Suppression 不被覆盖；新永久失败/拒收事件可新增一条 active 记录，旧历史仍保留。
- Projected Suppression 在 Preview 时扣除已有 active email Suppression，并按邮箱去重。

## 11. API

- `POST /api/v1/umail-result-imports`：multipart CSV + 可选 Mapping；只解析、关联、保存预览。
- `GET /api/v1/umail-result-imports/{import_id}`：恢复 Import、计数、Mapping 与应用结果。
- `GET /api/v1/umail-result-imports/{import_id}/rows`：分页，并按 match status、event type、Campaign、Suppression impact 过滤。
- `POST /api/v1/umail-result-imports/{import_id}/apply`：请求体必须为 `{"confirmed": true}`；重复 Apply 幂等。
- `GET /api/v1/umail-result-imports/{import_id}/statistics`：返回 Import、Campaign、Route tier、Company 的 Engagement 统计。

Route 仅做 HTTP 验证和 schema 映射；业务逻辑位于 Workflow，SQL 只位于 Repository。

## 12. 前端

新增独立“Umail 结果回传”Panel，可在没有当前 ImportSession/RoutingRun 时单独使用：

- CSV 选择与 Mapping JSON；
- 文件 SHA-256、总行数、Mapping 快照；
- matched/unmatched/ambiguous/invalid/duplicate 预览；
- 预计追加事件和预计新增 Suppression；
- 明确人工确认 checkbox 后才允许 Apply；
- 行级邮箱、Campaign、事件、关联来源、Suppression 影响与排除原因；
- match/event/Campaign/Suppression 过滤和分页；
- Apply 后的 Campaign、Route tier、Company 统计；
- URL 参数 `umail_result_import_id`，刷新恢复完整结果；
- 中英文文案完整；核心中文警告为：“导入的是外部发送结果，不代表本系统发送了邮件。”

## 13. 统计

从 append-only Engagement 实时计算：

- 总结果行数与 matched rate；
- delivered、reply、hard bounce、unsubscribe、complaint rate；
- 全部 event type 计数；
- 每个 Campaign 事件统计；
- 每个 Route tier 事件统计；
- 每家公司事件统计。

本轮只展示反馈数据，不修改 Pre-Score、Opportunity 或 A/B/C/D Route，不触发 Follow-up。

## 14. 性能

真实 PostgreSQL 合成样本：10,000 条结果行，其中 7,000 matched、1,000 unmatched、500 ambiguous、1,000 invalid、500 duplicate；8,000 个 ExportRow 快照；事件混合 10 类，其中包含 hard bounce、unsubscribe、complaint 和 reply。

实测：

- parse + match：`3.813s`（目标 `<30s`）；
- Apply：`2.634s`（目标 `<30s`）；
- 峰值 Python tracked memory：`61.2 MiB`（目标 `<256 MiB`）；
- SQL：Upload `10` 条、Apply `11` 条，数量不随行数线性增长，无 N+1；
- 创建 Engagement：7,000；
- 创建 Suppression：2,100。

## 15. 测试门禁

- Backend full pytest：`1196 passed`。
- Ruff：通过。
- strict mypy：`417 source files`，通过。
- D5d2b 领域/CSV/Workflow/PG API/性能定向：通过。
- 四级匹配、unmatched、ambiguous、文件/行/事件/Apply 幂等：通过。
- 全部 10 类 Engagement、三类自动 Suppression、inactive 重新激活：通过。
- Preview 无 Engagement/Suppression 副作用：通过。
- ExportRow、Outreach.sent_version、Draft、Outcome 不变：通过。
- Migration upgrade/downgrade/upgrade：`2 passed`。
- `alembic current` / `heads`：单一 `d5d2b1c2d3e4 (head)`。
- `alembic check`：`No new upgrade operations detected.`
- Frontend ESLint：0 error，5 个 D5d2b 之前已存在 warning。
- Frontend production build / TypeScript：通过。
- E2E TypeScript：通过。
- Playwright Chromium 定向：`1 passed`。
- 本地 HTTP smoke：Backend health 200、反馈上传缺文件返回预期 422、Frontend 200。
- Docker：Backend/PostgreSQL/Redis/Worker healthy，Frontend running。

## 16. 安全

- 未读取或输出 `.env`、密码、连接串、Token 或真实邮箱文件。
- 测试和 E2E 全部使用 `example.test` 合成数据。
- 不提交真实 Umail 结果文件、dump、截图、Playwright report 或临时 smoke 文件。
- 普通应用日志不输出完整邮箱；测试 HTTP 日志只记录路径与状态。
- 原始 CSV 行只保存于受控 PostgreSQL JSONB，不写普通文件日志。
- ambiguous/unmatched/invalid/duplicate 不自动 Apply。
- 不调用 Umail API、真实 LLM、Research Provider 或任何外部服务。
- 不发送邮件，不创建发送记录，不修改 `Outreach.sent_version`。

## 17. 兼容

- 保持 Domain 无 FastAPI/SQLAlchemy/Pydantic 依赖。
- Route 无业务逻辑；Workflow 编排；Repository 返回 Domain/read model，不暴露 ORM。
- Provider 不访问 Repository；本功能没有 Provider 调用。
- 新 Migration 线性接在 D5d2a 后，单一 head；历史 Migration 未修改。
- 现有 Umail Export V1、Suppression 手工管理、D5a–D5d1、MVP 分析和 Research 路径保持兼容。
- 新开发库从 D5d2a 正常升级到 D5d2b；legacy 数据库和 dump 保持不变。
- PR #4 Calibration 保持冻结。

## 18. 新增技术债

1. 结果来源仍为手工文件上传和 Mapping，不接 Umail API。
2. 20,000 行以内采用同步 HTTP 解析、匹配和 Apply，没有后台 job/progress。
3. 原始行保存在主 PostgreSQL；当前尚无多租户授权、字段级保留期或对象存储归档。
4. 统计限定于单次 ResultImport，没有跨 Import/Campaign 的长期分析视图。
5. event type 别名和 CSV Mapping 版本仍需真实 Umail 文件持续验证。

## 19. 债务保留理由

1. 文件上传能在不增加认证、外部依赖和 API 契约风险的情况下验证真实结果闭环。
2. 性能样本显著低于 30 秒和 256 MiB 门槛，引入 worker 暂无收益证据。
3. 当前 MVP 是单用户本地/受控环境；先保留可追溯原始行，便于解释解析与关联。
4. 单 Import 统计已足够验证反馈价值；跨 Campaign BI 会扩大产品范围。
5. 真实 Umail 导出字段仍可能变化，先版本化 Mapping 比硬编码外部格式更稳妥。

## 20. 债务偿还条件

1. 真实业务连续使用且 Umail API 的认证、字段和限流合同稳定后，增加 API 自动拉取适配器。
2. 单文件经常接近 20,000 行、同步请求接近 30 秒或需要多人并发时，迁移到现有 PostgreSQL job/worker 模式。
3. 引入真实身份/多租户或合规保留期要求时，增加租户边界、授权、脱敏和归档/删除策略。
4. 至少积累多个 Campaign 和重复联系人反馈后，再建立跨 Import 聚合与校准读模型。
5. 收集足量真实 Umail 文件并确认字段稳定后，发布 Result Contract 新版本，而不是静默修改 V1。

## 21. 未完成事项

本轮按范围明确未实现：

- Umail API 与自动结果拉取；
- 邮件发送、发送队列和发送记录；
- bounce/unsubscribe/complaint 自动 API 导入；
- 自动 Follow-up；
- 自动邮箱验证；
- 新 LLM/Provider；
- 自动修改 Pre-Score、Opportunity 或 Route tier；
- Calibration；
- 对象存储；
- 跨 Campaign 长期分析与 CRM。

## 22. D5e 真实闭环验收建议（未实施）

建议 D5e 只做一次小规模、可回滚的真实闭环验收：选取已人工确认的 B 类公司生成 Umail CSV；由用户在 Umail 外部手工发送；导出真实结果文件；通过 D5d2b 上传、预览、人工 Apply；核对 ExportRow 关联准确率、Engagement 完整性、Suppression 正确性和销售可解释性。验收前固定成功标准，包括：强 ID 关联覆盖率、ambiguous 人工处置率、永久失败 Suppression 准确率、无误发送/误标记、无 ExportRow/Outreach/Draft 污染。D5e 不应同时引入自动发送、自动 Follow-up 或自动 Calibration。
