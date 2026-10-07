# D5e1 真实数据闭环验收准备报告

## 1. PR #10 合并状态

- PR #10 `feat(feedback): add offline Umail result feedback loop` 已通过最小合并门禁并
  使用 Squash Merge 合并。
- Merge commit：`b0b92b0b7a7481dc4b06c58ce1d8645de664b13d`。
- 合并前确认 OPEN、MERGEABLE、CLEAN、GitHub check SUCCESS，分支与远程一致，
  工作区干净，`git diff --check`、单一 Alembic head 和 `alembic check` 均通过。
- D5d2b 定向门禁 `6 passed`；Preview/Apply/幂等/不可变性/不发送边界有代码和测试证据。
- PR #4 Calibration 仍为 OPEN，head 与更新时间均未变化。
- 合并后本地 `main` 与 `origin/main` 一致；当前新开发库升级到
  `d5d2b1c2d3e4 (head)`，legacy 数据库和既有 dump 未修改。

## 2. D5e1 实现结论

状态：`D5E_WAITING_FOR_REAL_FILES`。

D5e1 已完成真实数据验收所需的只读工具、Mapping Profile、数据质量聚合报告、
本地安全门禁、轻量前端步骤导航、运行手册和合成测试。当前没有用户真实网易文件或
真实 Umail 结果文件，因此没有执行真实导入、人工抽样、外部 Umail 发送或真实闭环
Apply，也没有把合成结果描述为真实验收成功。

本轮未新增核心业务模型，未新增 Migration，未修改历史 Migration，未修改
Pre-Score、Opportunity 或 A/B/C/D 路由规则。

## 3. 为什么 D5e 是验收而非新功能阶段

D5a–D5d2b 已具备 Raw Import、Entity Resolution、Routing、A 类深度处理、B 类
CSV 导出、Suppression 和 Umail 结果回传。D5e1 只在这些现有边界上增加：

- 写入前的只读文件检查；
- 可人工确认的字段 Mapping；
- 聚合数据质量报告；
- 真实数据执行的显式安全确认；
- 现有页面顶部的十步验收导航；
- 可复现运行手册和测试门禁。

没有创建第二套业务系统，也没有引入 Umail API、自动发送、Follow-up、Calibration、
对象存储或新的 Provider。

## 4. 网易 Preflight

新增 `POST /api/v1/acceptance/netease-preflight` 和本地 CLI：

```bash
cd apps/backend
uv run python scripts/acceptance_preflight.py netease /ignored/path/source.csv
uv run python scripts/acceptance_preflight.py netease /ignored/path/source.xlsx
```

只读输出：

- CSV/XLSX 类型、字节数、SHA-256、编码、Sheet 列表和选择的分析 Sheet；
- 总行数、分析行数和 company/contact/shipment/mixed/unknown 类型推测；
- 自动 Mapping、Mapping 置信来源、未知字段、必填缺失和重复列；
- 空行、无效行、公司/联系人/贸易记录估计；
- external company ID、email、website/domain、phone、address 覆盖率；
- 高置信与中置信人工复核估计。

Preflight 服务无 Repository、Provider 或外部 HTTP 依赖，不创建 ImportSession、
RawImportRow、Company、Contact、Opportunity、Research、Route、Draft 或邮件活动，
也不返回或记录原始行内容。

## 5. Umail Preflight

新增 `POST /api/v1/acceptance/umail-result-preflight` 和本地 CLI：

```bash
cd apps/backend
uv run python scripts/acceptance_preflight.py umail /ignored/path/results.csv
```

输出文件 hash、编码、总行数、Mapping、未知/缺失/重复列、事件分布、时间格式分布、
bounce 分布、export row/batch ID、email、campaign 覆盖率、不支持事件、缺失时间和
无效行。

API 在 Mapping 足够且文件结构可进入现有 D5d2b 合同时，会只读查询不可变
UmailExportRow 快照，并按 D5d2b 同一优先级计算：

1. `export_row_id` 强 ID 实际预计匹配数；
2. batch/campaign/email/time-window fallback 实际预计匹配数；
3. ambiguous 实际预计行数。

该查询不创建 ResultImport、ResultRow、Engagement、Suppression、Outcome 或发送记录，
也不 commit。CLI 不连接数据库，因此明确标记为 `file_identifiers_only`；API 成功读取
当前导出快照时标记 `database_snapshot`，避免把结构完整度冒充实际可匹配率。

## 6. Mapping Profile

- 网易 Profile：`netease-foreign-trade-v1`。
- Umail Profile：`umail-result-preflight-v1`。
- 模板：
  - `docs/templates/netease-foreign-trade-v1.mapping.json`
  - `docs/templates/umail-result-preflight-v1.mapping.json`

网易支持英文、常见中文列名和用户人工覆盖，包括 company、external/company ID、
website/domain、address/country、contact/title/email/phone、HS/product/date、
quantity/weight/amount、POL/POD。模板只是逻辑字段清单，不假定真实网易或 Umail
固定使用模板列名。真实正式导入必须显式提交经用户确认的 Mapping。

## 7. 前端验收入口

现有 Bulk Import 页面顶部增加轻量“真实闭环验收”导航，不新建 Dashboard：

1. 网易文件 Preflight
2. Mapping 确认
3. ImportSession
4. Entity Resolution
5. Routing
6. A/B 处理
7. Umail Export
8. Umail Result Import
9. Apply
10. Closure Report

页面显示当前步骤、Raw/Company/Contact/Route 数量、阻塞字段、需要用户确认的 Mapping、
真实/合成数据模式、真实 Provider 未调用状态和系统不发送邮件状态。既有
ImportSession、RoutingRun、Batch、ExportBatch、ResultImport 继续通过 URL ID 恢复；
真实数据模式通过 URL 恢复。Preflight 本身保持只读且不保存原始文件，刷新后需要用户
重新选择文件，这是避免把真实文件复制到浏览器存储或业务数据库的安全取舍。

## 8. 安全门禁

- 新增本地 `real_data_acknowledged` 配置，默认关闭。
- Preflight 在门禁关闭时仍可运行，因为它无业务副作用。
- 正式真实 NetEase ImportSession 和真实 Umail ResultImport 必须同时满足：
  - 请求明确为 real-data mode；
  - Mapping 非空且用户明确确认；
  - 本地安全确认已启用。
- 真实 Umail ResultImport 的明确 Apply 会再次携带 real-data mode；若本地安全确认缺失，
  Apply 在进入写入 Workflow 前同样被拒绝。
- 缺失 Mapping 确认返回 `real_data_mapping_confirmation_required`。
- 缺失本地安全确认返回 `real_data_acknowledgement_required`，写入 Workflow 不执行。
- 页面和报告只显示门禁 enabled/blocked，不显示 `.env` 内容、连接信息或凭据。
- 所有测试数据使用 `example.test`；未读取、复制或提交真实文件和完整邮箱列表。

## 9. 测试

代码测试与合成数据结果：

- Backend full pytest：`1204 passed in 99.40s`（最终门禁复跑）。
- Ruff：通过。
- strict mypy：`424 source files`，通过。
- D5e1 CSV/XLSX、mixed、gb18030、异常编码、空文件、别名、人工 Mapping、
  Umail 分布、只读副作用、安全门禁和 DB 快照匹配估计：通过。
- 最后一次安全门禁变更定向回归：`8 passed`；此前 D5a1、D5d2b 定向回归：
  `29 passed`。
- Migration scratch DB upgrade/downgrade/upgrade：随 full pytest 的 `2 passed`。
- Alembic current/head：`d5d2b1c2d3e4 (head)`；单一 head；`alembic check` 通过。
- Frontend lint：0 error；5 个 D5e1 之前已存在 warning。
- Frontend TypeScript / production build：通过。
- Playwright Chromium：D5e1 Preflight/刷新恢复 + D5d2b 回传回归 `2 passed`。
- E2E 使用 throwaway database，结束后数据库已删除。

真实数据结果：未执行。真实 Umail 文件结果：未执行。人工抽样：未执行。

## 10. 是否新增 Migration

否。D5e1 没有新增表、列、索引或约束，也没有修改 D5a–D5d2b 历史 revision。
数据库生命周期测试在独立 scratch database 完成；当前新开发库保持 D5d2b head，
legacy 数据库未迁移、未写入、未删除。

## 11. 性能

合成网易 CSV 20,000 行（上限规模）只读 Preflight：

- 用时：`0.454s`；
- Python tracked peak memory：`19.4 MiB`；
- 结果：20,000 公司估计、20,000 联系人估计；
- 数据库 SQL：0；
- Provider/外部 HTTP：0。

该结果只证明合成格式下的代码性能，不代表真实网易 XLSX 的最终表现。真实文件到达后
需记录文件大小、Sheet 数、行数、实际用时和内存，并单独标注真实结果。

## 12. 技术债

1. XLSX 当前只支持只读 Preflight，正式 ImportSession 仍维持已验证的 CSV 合同。
2. 本地 CLI 的 Umail 匹配估计只基于文件标识符；只有 API 会读取当前数据库导出快照。
3. Preflight 报告不持久化；刷新后需重新选择文件并再次确认 Mapping。
4. 别名表尚未用真实网易和真实 Umail 文件校准。
5. Closure Report 当前由运行手册定义，尚无真实运行可生成最终验收结论。
6. real-data mode 是本地受控验收中的显式请求状态，不写入新的业务模型；真实运行期间
   必须保持页面 URL 中的 real-data mode，上传与 Apply 都会据此执行本地安全门禁。

保留理由：没有真实格式证据时扩展正式 XLSX 导入、持久化原始文件或固化更多别名会
增加错误解析、敏感数据复制和范围膨胀风险。现有只读工具已经能够安全暴露真实格式差异。

偿还条件：用户提供真实文件后，仅针对确认存在的格式差异做最小兼容修复；如文件规模、
同步耗时或多人并发超过当前边界，再评估后台任务或受控对象存储。

## 13. 等待用户提供的文件

- 一份原始、未修改的网易外贸通 CSV 或 XLSX；建议首轮只处理 100–300 家公司、
  500–2,000 个联系人及对应贸易记录。
- 在 Umail 外部手工发送后导出的真实结果 CSV。
- 如 Umail 导出版本支持自定义列，需同时说明用户实际选择的字段集合。

原始文件必须保存在 Git 忽略目录，不得提交仓库或复制到测试 fixture。

## 14. 用户需要执行的动作

1. 将真实网易文件放入本地 Git 忽略目录。
2. 在页面或 CLI 运行只读 Preflight，将聚合结果交给 Codex/开发者复核。
3. 确认 Mapping 和受控样本范围；如为 XLSX，先根据真实结构决定最小兼容方案。
4. 明确授权本地真实数据执行，并完成安全门禁配置。
5. 完成 B 类 Umail CSV 外部手工发送后，提供真实 Umail 结果 CSV。
6. 如需真实 LLM Provider，另行明确授权，且最多两家公司。

## 15. D5e2 真实运行步骤

1. 网易 Preflight；记录 hash、格式、行数、Mapping、覆盖率和阻塞项。
2. 用户确认 Mapping；必要时只做真实格式暴露的最小兼容修复并重新过门禁。
3. 受控创建 ImportSession/RawImportRow，验证有效率和逐行 error code。
4. Entity Resolution；抽样验证 external ID、domain、email 与 CompanyContact 追溯。
5. Routing；核对全部 tier/reason/blocked，A 最多 3–5 家，B 选 20–50 联系人。
6. A 类默认 Website HTTP + deterministic Provider；真实 Provider 另行授权且最多两家。
7. 生成 B 类 Umail CSV，核对 ready/suppressed/invalid/duplicate，不标记发送。
8. 用户在 Umail 外部手工发送并导出真实结果文件。
9. Umail Preflight；核对数据库快照强 ID/fallback/ambiguous 预计比例并确认 Mapping。
10. 现有 D5d2b 上传 Preview；人工审查后明确 Apply。
11. 核对 Engagement、Suppression、幂等和 ExportRow/Draft/Outreach 不污染。
12. 输出最终 Closure Report，分别记录真实网易、真实 Umail、人工抽样和未验证项。

在上述真实步骤完成前，项目状态保持：`D5E_WAITING_FOR_REAL_FILES`。
