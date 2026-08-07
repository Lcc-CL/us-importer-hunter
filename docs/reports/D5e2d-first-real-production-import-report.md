# D5e2d First Real Production Import 报告

日期：2026-08-07

## Status

**WAITING_FOR_USER_REAL_IMPORT** —— 所有写前验收就绪，真实导入等待用户在
生产页面亲自点击；Codex 不模拟用户确认。

## 0. PR 门禁

- PR #16（D5e2c）已 Squash Merge（main=`0942cd2`），本地 == origin/main，
  工作区 clean；Alembic 单 head `d5d2b1c2d3e4`；PR #4 未触碰（OPEN）。

## 1. Production Safety Snapshot

- 备份：`/private/tmp/uih-d5e2d-backup-20260806-235140.sql`（154,619 B，
  pg_dump -Fp 完整头尾，未入 Git，未输出凭据）。
- Alembic：current == heads == `d5d2b1c2d3e4`。
- 导入前计数（全部为 0）：import_sessions、raw_import_rows、companies、
  company_external_identities、contacts、company_contacts、
  import_entity_decisions、normalized_shipments、import_evidence_signals、
  import_evidence_raw_records、prospect_routes、opportunities、email_drafts、
  umail_export_batches。

## 2. 真实文件 Preflight（无漂移）

`2026-08-07_fitness_equipment.xlsx`（SHA-256 `aabf7664…77fd`）：
Raw rows 127 · Company anchors 55 · Estimated companies 53 ·
Estimated contacts 123 · Company summary evidence 55 · True shipments 0 ·
Invalid 0 —— 与 D5e2b.2/D5e2c 完全一致，无
`REAL_IMPORT_PREFLIGHT_DRIFT`。

## 3. Mapping Finalization

11 个必需字段全部自动映射（HIGH）：company_name、website、contact_name、
contact_email、contact_title、hs_code、product_description、supplier
（largest_supplier）、amount（import_value）、country（country_or_region）、
last_import_at。未映射列（是否中国进口/中国·总进口次数/保存时间/联系人级别）
保留在 RawImportRow，不强行造语义。Mapping 版本/指纹以 Preflight
`mapping_profile=netease-foreign-trade-v1` + 文件 SHA-256 记录。

## 4. Department Contact Semantics

- Schema 已支持：`company_contacts.is_department_contact` + `reason_codes`；
  归并流程已通过 `is_department_email` 识别共享邮箱（info@/sales@/contact@
  等）并落 `is_department_contact=true`（不删除、不伪装自然人）。
- 本轮新增最小修复：决策人选择工作流排除部门共享邮箱
  （`_is_department_mailbox`），保证 info@/sales@ 等**不会被自动选为 Decision
  Maker**（D5e2d 分支/PR，待合并部署后生效）。
- 完整 contact_type / person-vs-department 一等模型记为技术债。

## 5. Company Merge Confirmation

Resolution Preview 两组 HIGH 归并（同域名+同名称）：
rows 49/51（mpiproducts.com）、rows 56/58（cevians.com）。由用户在 UI 复核
确认，后台不绕过。

## 6. System Gate

生产 runtime `real_data_gate=blocked`（SYSTEM GATE DISABLED，保持关闭）。
正规启用入口 = 管理员在 Backend 服务环境设置 `REAL_DATA_ACKNOWLEDGED=true`
（现有正式配置方式足够，不新增 Admin UI）；本轮不启用、不绕过。

## 7–14. 待用户导入后执行

用户完成 UI 导入后，继续验证：persisted counts（ImportSession=+1、
Raw=+127、Company 51/2/0、Contact 123/4/9、CompanyContact 123、Summary 55、
Shipment 0、Invalid 0）、幂等（同文件再上传不创建第二份 Canonical）、
追溯抽样（3 Company / 3 Person / 3 Department / 2 merge groups / 3 summary）、
Routing A/B/C/D dry-run、A Batch（≤5 家/批，仅第一批）、B Umail Export Preview
（不发送）、刷新恢复与 Worker/Backend 健康。本报告后续更新。

## 15. Tests（本阶段）

决策人排除部门邮箱：新增用例通过（8 passed）；Ruff / strict mypy 通过；
Preflight 无漂移校验通过；无需重跑无关全仓测试。

## 技术债

chunk/batch parser 非 streaming；完整 Employment History；fuzzy company ML
matching；contact_type 一等模型；Umail API；自动邮件发送；分布式 ingestion
queue —— 当前 20k 行目标无需，记录不修。
