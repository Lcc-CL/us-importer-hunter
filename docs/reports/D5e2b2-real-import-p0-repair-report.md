# D5e2b.2 Real NetEase Import P0 Repair 报告

日期：2026-08-06

## Status

四个 P0 均已修复并通过测试与真实文件 Preflight；**仍然只读**：未创建真实
ImportSession、未写 Company/Contact/Evidence/Route/Opportunity/Draft/Export、
未发送邮件。正式导入等待用户亲自确认。

## A. XLSX 正式导入

- 统一 `TabularReader`（CSVTabularReader / XLSXTabularReader）输出统一
  `sheet_name / row_number / raw_payload / source_columns`；ImportSession/
  RawImportRow/Entity Resolution/Routing 不感知格式。
- `ImportSession.file_type ∈ {csv, xlsx}`；文件 hash 幂等覆盖两种格式，同一
  XLSX 重复上传不产生第二个 active ImportSession（唯一约束 + 复用逻辑）。
- 复用同一套解析语义（真实文件 492 个合并单元格、无隐藏行均正确解析）；
  batch/chunk parsing 保留为已接受技术债。

## B. 72 个 contact continuation rows

- 法证：55 个公司锚点行 + 72 个联系人续行，全部被公司列垂直合并范围覆盖；
  `grouping_rule=xlsx_vertical_merge`、`grouping_confidence=high`、
  `company_anchor_source_row` 溯源；禁止无证据 forward-fill（无合并证据 →
  orphan / review_required）。
- Preflight 修复前 invalid=72（XLSX 稀疏行未按表头补齐导致列数误判），已修复
  （数据行按 headers 补齐）；真实文件重新只读统计：

| 指标 | 值 |
| --- | --- |
| raw_rows | 127 |
| company_anchor_rows | 55 |
| contact_continuation_rows | 72 |
| linked_contact_rows | 72 |
| orphan_contact_rows | 0 |
| invalid_rows | 0 |
| estimated_companies | 53 |
| estimated_contacts | 123 |
| company_import_summary_rows | 55 |
| true_shipment_rows | 0 |

UI 不再把续行显示为“无效行”（统计卡改为 原始行/公司 Anchor/联系人续行/公司
估计/联系人估计/待人工复核/真正无效；高置信归并/待人工归并明确标注）。

## C. Deterministic aliases

通用 alias registry（非 filename-specific）：公司名称、官网、联系人姓名、
联系人邮箱、联系人职位、HS code/HS Code、主要进口产品、最大供应商、进口金额、
国家/地区、最后进口时间均自动识别。exact → HIGH；fuzzy → MEDIUM。

真实文件验证：contact_email→联系人邮箱 HIGH、contact_title→联系人职位 HIGH、
last_import_at→最后进口时间 HIGH；11 个字段自动映射，5 个保留 Raw
（是否中国进口/中国/总进口次数/联系人级别/保存时间）。

## D. 不创建 fake shipment

- grain 判定：公司级 import summary（字段为 HS/主要进口产品/最大供应商/进口
  金额/国家/最后进口时间），`true_shipment_rows=0`；
- `record_kind=company_import_summary`；归一化 payload 含 hs_code、
  main_import_product、largest_supplier、import_value_raw、country_or_region、
  last_import_at；无明确币种 → `currency=unknown`，不假定 USD/RMB；不生成
  fake shipment/shipment_date/supplier transaction。

## E–I. UI 语义

- Mapping UI：公司摘要文件下“贸易记录”组自动显示为“公司进口摘要”+
  提示文案+“真实逐票贸易记录 0”；逐票文件才显示原 Shipment Mapping。
- 统计卡：原始行/Anchor/续行/估计/待复核/真正无效，不再单独显示“无效行 72”。
- 置信度：拆为 `mapping_source`（auto_alias/manual/inferred）+ `mapping_confidence`
  （HIGH/MEDIUM/LOW），Manual 不再出现在置信度栏。
- 真实数据门禁两层：SYSTEM GATE（real_data_acknowledged 管理员开关，UI 显示
  启用/禁用）与 USER CONFIRMATION（用户勾选）；系统关闭时按钮旁显示
  “系统真实数据导入开关当前关闭，需要管理员启用。”，checkbox 不能控制管理员
  开关。
- Step 语义：区分“正式已导入实体（Raw/Company/Contact/Route）”与
  “Preflight estimate（53 companies · 123 contacts）”。

## J. 只读

本轮未写任何业务数据；真实文件仅用于只读 Preflight。

## K. 测试

- 新增/更新：XLSX 解析、CSV 回归、同 XLSX 幂等（PG 集成）、contact continuation
  grouping、orphan contact、无跨公司 forward-fill、email/title alias、
  company import summary、no fake shipment、unknown currency、system gate vs
  user acknowledgement（UI 断言）、mapping confidence/source 分离、Preflight
  estimate vs persisted 标签。
- 结果：单元 22 passed；PG 集成 6 passed（含 XLSX 幂等与迁移测试）；Ruff 通过；
  strict mypy 通过（7 files）；Alembic 无 drift、单 head `d5d2b1c2d3e4`
  （无新增 Migration）；前端 tsc/ESLint(0 error)/build 通过；定向 Playwright
  14/14（干净 E2E 库）。

## L. 真实文件 Preflight Acceptance

见 B 表；`contact_email mapped = 是(HIGH)`、`contact_title mapped = 是(HIGH)`；
72 行不再被分类为 invalid。

## 合规

未写生产库；未调用外部 Provider/LLM/Umail；未发送邮件；报告不含完整联系人邮箱。
