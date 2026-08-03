# D5d2a Umail CSV Export & Suppression Report

Date: 2026-08-02  
Branch: `feat/umail-export-suppression-foundation`

## 1. 实现结论

D5d2a 已完成。系统现在可以从当前 ProspectRoutingRun generation 中选择已确认或人工覆盖的 effective B 公司，确定性选择每家公司最多两位联系人，应用 email/domain/company Suppression、无效邮箱检查和批次内邮箱去重，持久化不可变导出快照，提供刷新可恢复的预览，并按固定 UmailExportContractV1 下载 CSV。

本实现不调用 Umail API、不调用 LLM 或其他外部 Provider、不创建发送记录、不修改 `Outreach.sent_version`、不创建 Outcome，也不把任何 Prospect 标记为已发送或已触达。

## 2. 旧数据库统计

归档前旧本地开发库已知并复核的关键统计：

| 对象 | 数量 |
| --- | ---: |
| 表 | 49 |
| ImportSession | 0 |
| Company | 13 |
| Contact | 13 |
| Research | 56 |
| 人工 Promotion | 25 |
| Opportunity | 13 |
| Draft | 8 |
| 已审核 Draft | 7 |

旧库包含 D5c schema drift，因此未在该库继续执行历史 Migration 或 schema repair。

## 3. dump 恢复验证

- Dump 位于 Git 忽略目录：`e2e/.cache/local-db-backups/local-dev-before-d5d2a-20260802.dump`。
- 文件大小：225,909 bytes。
- Catalog entries：326。
- SHA-256：`e112d8d92652fe440ea6814b52e14e5985b7ada49c570d7313862309ec746182`。
- 已恢复到独立临时验证数据库；未使用生产或当前开发数据库名称。
- 恢复后验证：Company 13、Contact 13、Research 56、Promotion 25、Opportunity 13、Draft 8、已审核 Draft 7。
- 关键表均可正常 SELECT。
- 临时恢复数据库已删除；原 dump 保留且未修改。

结论：`BACKUP_RESTORE_VERIFICATION_PASSED`。

## 4. legacy 数据库归档状态

- 旧开发库已保留为安全别名：`importer_hunter_legacy_20260802`。
- legacy 库未删除、未执行 Migration、未进行业务写入。
- D5d2a 完成后只读复核：Company 13、Contact 13、Research 56、Opportunity 13、Draft 8、已审核 Draft 7，计数未变化。
- 未输出数据库密码、连接串或 `.env` 内容。

## 5. 新开发数据库创建状态

- 使用原开发数据库名称创建全新空库，现有安全配置无需改名。
- 从当前代码的完整 Alembic chain 初始化，而不是复制旧库 schema。
- D5d2a 开发期间最终 Migration 增加 active Suppression 唯一索引；由于开发库当时仍为空，停止 Backend/Worker 后再次安全重建空开发库，并从最终 head 全量初始化，避免任何临时 schema repair。
- 当前 D5d2a 业务表均为空：SuppressionEntry 0、UmailExportBatch 0、UmailExportRow 0。
- Backend、Worker、Frontend 已连接该新开发库并正常运行。

## 6. Alembic 和 schema 验证

- 新 Revision：`d5d2a1b2c3d4`。
- Down revision：`d5c1f2e3a4b6`。
- 未修改任何已进入 main 的历史 Migration。
- `alembic heads`：单一 head `d5d2a1b2c3d4`。
- `alembic current`：`d5d2a1b2c3d4 (head)`。
- `alembic check`：`No new upgrade operations detected.`
- 专用 scratch PostgreSQL Migration 测试完成 upgrade / downgrade / upgrade。
- 最终空开发库从 base 到 head 全量初始化成功。

新增表：

- `suppression_entries`
- `umail_export_batches`
- `umail_export_rows`

主要数据库约束：

- Suppression 恰好一个 target；active/inactive 与停用审计一致。
- active email/domain/company 分别使用 partial unique index，停用后可重新建立同 target 条目。
- Batch 状态、generation、统计总和、下载时间和 selection hash 唯一性受数据库约束保护。
- Row 只允许 B、只允许 confirmed/overridden、固定正 position、状态与排除原因一致。
- `(batch_id, position)` 和 `(batch_id, row_fingerprint)` 唯一。

## 7. D5d1 合并状态

- PR #8 已通过门禁并使用 Squash Merge 合并。
- Merge commit：`46b72685b2be391ccba16afccb8bc699d3baf30d`。
- 合并后本地 `main` 与 `origin/main` 一致，再由该 main 创建 D5d2a 分支。
- PR #4 Calibration 保持 OPEN 和冻结，未修改、未合并。
- 未创建 release tag。

## 8. Git / PR

- 功能分支：`feat/umail-export-suppression-foundation`。
- Commit message：`feat(umail): add auditable B-prospect CSV export and suppression`。
- PR 标题：`feat(umail): add B-prospect export and suppression workflow`。
- PR 在本报告随最终单一 Commit 推送后创建，保持 OPEN，不执行合并。

## 9. D5d2a 技术选型和理由

1. 使用独立 `umail_export` bounded context，避免把发送概念混入 ProspectRouting、Outreach 或 Contact。
2. Workflow 编排资格校验、联系人选择、Suppression、去重和 CSV；API Route 只做 HTTP 适配。
3. Repository 返回 Domain Aggregate 和导出候选 read model，不暴露 ORM。
4. 批次与行全部持久化为审计快照，下载时从快照确定性重建 CSV 并校验 SHA-256。
5. CSV 内容不写对象存储；MVP 上限为 1,000 ready 联系人，内存生成已满足性能预算。
6. 采用 UTF-8 BOM，兼顾中文字段和常见表格/Umail 导入工具。

## 10. 数据模型与 Migration

### SuppressionEntry

- `email` / `domain` / `company` 三选一。
- `active`、`reason`、`source`。
- `created_by`、`deactivated_by`、`deactivated_at`、`created_at`、`updated_at`。
- target 标准化为小写；公司名折叠空白并 casefold。

### UmailExportBatch

- Routing run 与 execution generation。
- Campaign、mapping version、selection hash。
- prepared/downloaded 状态。
- total/ready/suppressed/invalid/duplicate 统计。
- content SHA-256 与首次下载时间。

### UmailExportRow

- Company/Contact/Email 快照。
- effective route、route review status、pre-score 快照。
- personal/department contact 标识。
- ready/suppressed/invalid/duplicate 和排除原因。
- 稳定 position 与内容型 row fingerprint。
- 无更新 API；下载只读该不可变快照。

## 11. 联系人选择规则

1. 只读取请求 RoutingRun 的当前 generation。
2. 所有选择公司必须属于该 generation。
3. 只允许 effective B 且 review status 为 confirmed 或 overridden。
4. blocked、A、C、D 和 suggested 均返回冲突，不创建批次。
5. CompanyContact 和 Contact 必须 active；invalid/inactive Contact 不进入候选。
6. personal contact 排在 department contact 前；部门联系人只用于不足两人的 fallback。
7. 角色优先级：procurement、supply_chain、logistics、operations、import_export、executive、owner_founder、warehouse、general_department、unknown、sales、irrelevant。
8. 同角色按 seniority、姓名和 Contact ID 稳定排序。
9. 每家公司最多选择两位联系人。
10. 同一联系人按 manually_verified、source_verified、unverified、invalid 选择一个确定性 email 快照。

## 12. Suppression 规则

- active email 精确匹配标准化邮箱。
- active domain 匹配邮箱 `@` 后域名。
- active company 匹配标准化公司名，并抑制该公司全部候选。
- 状态优先级：公司 Suppression → 缺失/无效 email → email/domain Suppression → 批次内 duplicate → ready。
- 同一邮箱只有首个 ready row 可进入 CSV；后续 row 标记 duplicate。
- 创建和停用均保留操作者与时间审计。
- 已生成 Batch 不因后续 Suppression 变化而重写；新的准备请求将因 selection hash 变化创建新 Batch。

## 13. CSV Contract

Contract：`umail-export-contract-v1`。

固定列顺序：

1. `company_name`
2. `company_website`
3. `contact_name`
4. `contact_title`
5. `contact_role`
6. `contact_seniority`
7. `email`
8. `campaign`
9. `route`
10. `pre_score`

规则：

- 仅 ready row 进入 CSV；其他状态只在审计预览保留。
- UTF-8 BOM 编码。
- CRLF 行结束符。
- Python CSV writer 处理引号、逗号和换行。
- 以 `= + - @ tab CR` 开始的文本添加前导单引号，防止 formula injection。
- 重复下载从持久化 rows 重建；内容 hash 必须等于 Batch `content_sha256`，否则拒绝下载。

## 14. API

- `POST /api/v1/suppressions`
- `GET /api/v1/suppressions`
- `POST /api/v1/suppressions/{entry_id}/deactivate`
- `POST /api/v1/prospect-routing-runs/{routing_run_id}/umail-export-batches`
- `GET /api/v1/umail-export-batches/{batch_id}`
- `GET /api/v1/umail-export-batches/{batch_id}/download`

下载响应包含 CSV attachment、`X-Content-SHA256` 和 `X-Email-Sent: false`。

## 15. 前端

- 在销售路由区增加独立 D5d2a Panel。
- 展示并选择所有当前已确认/人工覆盖 B route；客户端自动分页读取最多 500 家路由。
- 支持 email/domain/company Suppression 创建和停用。
- 展示 ready/suppressed/invalid/duplicate 统计、逐行排除原因和部门 fallback。
- 支持 CSV 下载。
- URL 使用 `umail_export_batch_id`；刷新后恢复 Batch 和全部 row 快照。
- 中英文文案完整。
- 明确显示“已导出但尚未发送 / Exported but not sent”。

## 16. 性能结果

真实 PostgreSQL 定向样本：500 家 B 类公司、5,000 Contact、1,000 导出快照行。

| 指标 | 结果 | 预算 |
| --- | ---: | ---: |
| 导出准备 | 0.6570 s | < 30 s |
| CSV 生成 | 0.0015 s | < 10 s |
| tracemalloc peak | 12.24 MiB | < 128 MiB |
| SQL statements | 14 | 固定批量查询，无 N+1 |
| CSV bytes | 130,062 | 记录值 |

样本分类：ready 750、suppressed 100、invalid 100、duplicate 50。

## 17. 测试门禁

- Backend `pytest`：1188 passed。
- Backend Ruff：通过。
- Backend strict mypy：399 source files 通过。
- Migration scratch PostgreSQL upgrade/downgrade/upgrade：通过。
- `alembic current / heads / check`：通过，单一 head。
- D5d2a PostgreSQL API：通过。
- 500/5,000 性能样本：通过。
- Frontend ESLint：0 errors；保留 5 个与本任务无关的既有 warning。
- Frontend production build + TypeScript：通过。
- Playwright Chromium 定向：1 passed，覆盖刷新恢复、四种状态、Suppression 创建/停用、B 选择、CSV 下载和 no-send 文案。
- 修复了既有并发 ProspectBatch 测试使用独立 committed sessions 后未清理自身 fixture 的隔离问题；未修改产品逻辑。

## 18. 安全检查

- 未输出数据库密码、连接串、Token、`.env` 内容或个人凭据。
- 未修改 legacy 库。
- 未删除 dump。
- 仅删除临时恢复库、scratch Migration 库和 throwaway E2E 库。
- CSV formula injection 已防护。
- 未调用 Umail API、LLM、网站抓取或其他外部业务服务。
- 未发送邮件。

## 19. 兼容性

- 不修改已冻结一级目录。
- Domain 不依赖 FastAPI、SQLAlchemy、Redis 或 SDK。
- API Route 无业务决策。
- Repository 不暴露 ORM。
- 不删除 `Contact.company_id`，保持 CompanyContact 双轨兼容。
- 不修改 D5c/D5d1 历史表或 Migration。
- 不修改 Outreach、Outcome、Draft 发送语义。
- D5d1 A 类深度处理入口保持不变；D5d2a 只增加 B 类导出入口。

## 20. 新增技术债

1. Suppression 仅支持人工录入和停用，没有 bounce/unsubscribe/complaint 自动导入。
2. Email 只使用已有 verification status，不执行真实 mailbox verification。
3. CSV 在请求内存中生成，未使用对象存储或异步大文件生成。
4. 审计 actor 仍为客户端传入字符串，尚未绑定正式用户身份系统。
5. CompanyContact 与 legacy `Contact.company_id` 双轨继续存在。

## 21. 每项债务保留理由

1. 自动 Suppression 反馈依赖真实发送/回传；本轮明确禁止 Umail API 和结果回传。
2. 邮箱验证服务明确不在 D5d2a 范围，且不应伪造验证结果。
3. 1,000 ready 上限下 12.24 MiB 峰值远低于预算，引入对象存储会扩大 MVP 范围。
4. 当前项目没有正式认证/授权上下文，提前引入会形成跨域改造。
5. ADR-0022 与 D5b1 已明确保留兼容字段，本轮不得偿还该历史债。

## 22. 债务偿还条件

1. D5d2b 或后续 Umail 回传阶段引入 bounce/unsubscribe/complaint 数据时，增加自动 Suppression source 和幂等导入。
2. 决定接入邮箱验证 Provider 并明确成本/失败策略时，再新增验证 workflow。
3. 单批 ready 上限超过 1,000、CSV 超过内存预算或需要长期下载链接时，再引入对象存储/异步生成。
4. 用户认证落地后，将 created_by/deactivated_by 改为可信身份引用。
5. 完成 CompanyContact 全量迁移并有独立 ADR 时，再移除 legacy 联系字段。

## 23. 未完成事项

按本轮范围有意未实现：

- Umail API 调用和邮件发送。
- Umail 发送结果回传。
- bounce/unsubscribe/complaint 自动导入。
- Follow-up。
- 邮箱验证。
- 新 LLM Provider。
- Calibration。
- 对象存储。
- 自动标记 sent/contacted 或创建 Outcome。

## 24. D5d2b 建议（不得在本轮实施）

建议 D5d2b 聚焦“Umail 离线发送结果回传与 Suppression 闭环”，仍采用人工导入而不是立即接 Umail API：定义发送结果 CSV Contract，按 ExportBatch/Row fingerprint 幂等关联 delivery/bounce/unsubscribe/complaint，写入独立回传审计并更新 Suppression；在业务和数据质量稳定后再评估 API 自动化。D5d2b 不应在 D5d2a PR 内实现。
