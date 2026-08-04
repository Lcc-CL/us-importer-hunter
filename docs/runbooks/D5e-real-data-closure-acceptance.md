# D5e 真实数据闭环验收运行手册

## 目的与边界

本手册只用于受控的真实数据闭环验收。D5e 不新增业务模型，不接 Umail API，
不自动发送邮件，不自动 Follow-up，不自动改变 Pre-Score、Opportunity 或路由。
Website HTTP 只有在用户显式启动 A 类深度处理后才可能访问外部网站；Research 和
Draft 默认使用 deterministic Provider。未经用户再次授权，不启用真实 LLM Provider。

当前没有真实网易文件和真实 Umail 结果文件，因此 D5e 的真实验收状态必须保持
`D5E_WAITING_FOR_REAL_FILES`。

## 文件安全

1. 将真实文件放在仓库已忽略的本地目录，例如 `.local/acceptance/`。
2. 不修改源文件，不复制到 fixture，不提交 Git，不粘贴完整行到报告或工单。
3. 报告只保留 SHA-256、总量、覆盖率、分布和必要的脱敏样例。
4. 不在命令输出或报告中记录数据库连接信息、Token、完整邮箱列表或 `.env` 内容。
5. 第一次运行建议限制在 100–300 家公司、500–2,000 个联系人。

## 只读 Preflight

前端“真实闭环验收”入口提供两个只读 Preflight；两者都不会创建业务记录、调用
Provider 或发送邮件。也可以从 Backend 目录运行：

```bash
uv run python scripts/acceptance_preflight.py netease /ignored/path/source.csv
uv run python scripts/acceptance_preflight.py netease /ignored/path/source.xlsx
uv run python scripts/acceptance_preflight.py umail /ignored/path/results.csv
```

如需人工覆盖 Mapping，复制对应模板到 Git 忽略目录，按真实表头修改后传入
`--mapping /ignored/path/mapping.json`。仓库模板只是字段清单，不能假定网易或 Umail
固定使用模板中的列名。

## Step 1–2：网易 Preflight 与 Mapping

1. 上传 CSV/XLSX，只执行 Preflight。
2. 核对文件 hash、编码、Sheet、总行数、推测数据类型和 Mapping。
3. 处理未知字段、必填缺失、重复列、空行、无效行和覆盖率异常。
4. 核对公司、联系人、贸易记录估计及高/中置信复核估计。
5. 人工确认 Mapping。任何重复列或缺失 `company_name` 都应先阻止正式导入。
6. XLSX 当前仅完成只读预检；正式 ImportSession 保持既有 CSV 合同。拿到真实文件后，
   只有在确认 XLSX 是实际必需格式时，才做最小兼容修复，不能静默转换或修改源文件。

## 真实数据写入门禁

Preflight 始终可用。正式真实 ImportSession 或真实 Umail ResultImport 还必须满足：

1. 页面启用“真实数据模式”；
2. 用户明确确认当前 Mapping；
3. 本地运行环境已完成真实数据安全确认。

安全确认缺失时，API 返回 `real_data_acknowledgement_required`，且写入 Workflow 不会
执行。真实 Umail ResultImport 的明确 Apply 会再次检查该安全确认。真实运行期间不要
关闭页面的“真实数据模式”；该门禁只用于本地受控验收，不应在报告中记录环境变量的
实际内容。

## Step 3–10：受控闭环

1. 创建 ImportSession 并保存 RawImportRow。
2. 执行 Entity Resolution；人工处理所有中置信和高价值冲突。
3. 执行 Pre-Score 和 A/B/C/D Routing；核对每家公司 tier 与 reason codes。
4. A 类最多 3–5 家。默认 Website HTTP + deterministic Research/Draft；真实 Provider
   必须另获用户授权且最多两家公司，并记录调用次数、耗时、token 和失败原因。
5. B 类选择 20–50 个有效联系人，生成 Umail CSV；核对 Suppression、重复和无效行。
6. 用户在 Umail 外部手工发送。本系统不创建发送记录，也不标记已发送。
7. 用户导出真实 Umail 结果 CSV，先执行只读 Preflight。
8. 核对事件、时间、bounce 分布和 ID/email/campaign 覆盖率，再人工确认 Mapping。
9. 使用现有 D5d2b 上传预览；审查 matched/unmatched/ambiguous/invalid/duplicate。
10. 明确 Apply；只对 matched 行追加 Engagement 和必要 Suppression。
11. 输出 Closure Report，严格区分代码测试、合成数据、真实网易数据、真实 Umail
    文件、人工抽样和未验证项。

## 首次验收判定

- 有效行导入率至少 95%，单行错误不终止整批。
- external ID 与 normalized email 精确关联正确率 100%。
- domain 高置信归并人工抽样正确率至少 98%，中置信全部人工复核。
- 无效邮箱不进入 ready；同邮箱不重复导出；Suppression 生效。
- Umail `export_row_id` 精确关联正确率 100%；ambiguous 不自动 Apply。
- Preview 无业务副作用；Apply 幂等；ExportRow、Draft、Outreach 不被污染。
- 任何没有真实文件支撑的指标都标记“待执行/未验证”，不得由合成数据替代。
