# D5e2c First Real Import Pre-Write Acceptance 报告

日期：2026-08-06

## Status

READY_FOR_FIRST_REAL_IMPORT（代码/验收就绪，**本任务仍未执行任何真实 Import**；
SYSTEM GATE 保持 DISABLED，等待用户在 UI 完成 Mapping 确认、真实数据授权与
Resolution Preview 复核后自行导入）。

## 1. PR 门禁

- PR #15：OPEN → **已 Squash Merge**（`c8b3ffd`）；merge 前 OPEN/CLEAN/MERGEABLE、
  GitHub check `d5a1` SUCCESS。
- main 已同步：local == origin/main == `c8b3ffd`；工作区 clean；Alembic 单 head
  `d5d2b1c2d3e4`；PR #4 未触碰（OPEN，head 未变）。

## 2. Company 55 → 53 归并解释

55 个公司锚点 → 53 个 canonical 公司（2 组自动归并，全部有域名+名称双重证据）：

| 组 | source_row_ids | normalized_name | domain fingerprint | external_id | signals | rule | confidence | decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 49, 51 | mpi products deefield wisconsin llc | mpiproducts.com（相同） | 无 | same_normalized_name + same_domain | canonical_name_or_domain | HIGH | merge |
| 2 | 56, 58 | cevians llc 录入线索 | cevians.com（相同） | 无 | same_normalized_name + same_domain | canonical_name_or_domain | HIGH | merge |

无“仅名称相似”自动归并；无 brand/subsidiary/parent 冲突（company_review_count=0）。

## 3. Contact 123 对账

| 指标 | 值 | 说明 |
| --- | --- | --- |
| raw_contact_candidates | 127 | 每行都有联系人信息 |
| continuation_contacts | 72 | 合并单元格继承公司身份 |
| exact_duplicate_contacts | 8 行 / 4 组 | 同邮箱重复（含同公司重复锚点） |
| merged_contacts | 4 | normalized email + same company 自动合并 |
| review_required_contacts | 9 | 部门共享邮箱（info@/sales@/contact@ 等），不当作自然人自动合并 |
| invalid_contacts | 0 | — |
| final_estimated_contacts | 123 | 127 − 4 组邮箱去重 |

身份优先级：normalized email + same company（自动）→ LinkedIn（自动）→
name + company + title（MEDIUM/review）；仅同名不自动合并。

## 4. Resolution Preview（不 Apply）

- Company：51 create、2 merge（HIGH，见 §2）、0 review。
- Contact：123 create、4 merge、9 review（部门邮箱，保留为部门联系人并标记
  复核）。
- CompanyContact relations：123（每个 canonical contact-company 一条）。
- 全部为只读估算，未写数据库。

## 5. Expected production writes（dry-run，真实文件）

| 项 | 值 |
| --- | --- |
| Raw rows | 127 |
| ImportSession | 1 |
| Company create / merge / review | 51 / 2 / 0 |
| Contact create / merge / review | 123 / 4 / 9 |
| CompanyContact relations | 123 |
| Company import summary evidence | 55 |
| True shipments | 0 |
| Invalid rows | 0 |

## 6. Traceability 抽样（sheet / row / hash 均保留）

- 公司锚点：row 2（ACRA•••, hash 6fe9fff9…）、row 4（OCEA•••）、row 7（BEAU•••）
- 联系人续行：row 3 → inherited_from 2；row 5/6 → inherited_from 4
- 归并候选：邮箱 t•••@mpiproducts.com rows [49,51]；a•••@mpiproducts.com rows [50,52]
- Summary evidence：row 2 / row 4（record_kind=company_import_summary）

链路：ImportSession → RawImportRow（sheet/row_number/raw hash/grouping 元数据）
→ canonical entity decision → evidence，provenance 不丢失。

## 7. System / User Gate 矩阵

| SYSTEM GATE | USER CONFIRMATION | Preflight/Mapping/Preview | 允许 Import |
| --- | --- | --- | --- |
| OFF | ON | — | 否 |
| ON | OFF | — | 否 |
| ON | ON | 全部通过 | 是 |

本轮不开启 production gate（保持 DISABLED）；用户 checkbox 不能控制管理员开关。

## 8. UI Pre-Write Preview

正式导入按钮上方新增“即将写入（Preflight 估计）”：127 Raw rows · 53 Companies ·
123 Contacts · 123 CompanyContact · 55 Company summaries · 0 Shipments ·
2 Company merges · 4 Contact dedup · 9 Need review（数值来自 Preflight 字段，
非硬编码；区分 estimate 与 persisted）。

## 9. Remaining review items

1. 9 个部门共享邮箱联系人（确认是否保留为部门联系人/排除自然人归并）；
2. 2 组公司归并由用户在 Resolution Preview 中确认；
3. Mapping 最终确认（含 last_import_at 等 11 个自动映射字段）。

## 10. Technical debt（本轮不修）

- chunk/batch parser 非真正 streaming（20k 行目标无需）；
- 完整 Employment History；
- fuzzy company ML/entity matching；
- Umail API、自动邮件发送、分布式 ingestion queue。

## 11. Tests

单元 20 passed（含 resolution preview counts：归并/去重/部门邮箱/relations）；
PG 集成 4 passed（XLSX 幂等+CSV）；Ruff / strict mypy 通过；前端 tsc / ESLint
(0 error) / production build 通过；定向 Playwright 14/14（干净 E2E 库）；
Alembic 无新增 Migration、单 head。

报告不含完整真实联系人邮箱。
