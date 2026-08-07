# D5e2b.1 Real NetEase XLSX Import Semantics 修复报告

日期：2026-08-06

## Status

P0 修复完成（代码/测试/Preflight V2 就绪），**停在用户确认门禁**：未写入生产
数据库，未导入，未发送邮件。

## 1. 文件与结构法证

- 真实文件：`2026-08-07_fitness_equipment.xlsx`（104,581 B，
  SHA-256 `aabf7664…77fd`），sheet「客户线索」，127 行、16 列。
- workbook 结构：**492 个合并单元格**；无隐藏行；表头行冻结（row 1）。
- 行序列：55 个公司锚点行（row 2 起）+ 72 个联系人行，严格交替；
  **72/72 联系人行被公司列（A–K）的垂直合并范围覆盖**。
- 结构结论：`grouping_rule = xlsx_vertical_merge`，confidence = HIGH，
  lineage = 合并范围起始行（锚点行）→ 联系人行。无孤儿联系人。

## 2. 修复内容

- **统一 TabularReader**（`app/services/bulk_import/tabular.py`）：
  `CsvTabularReader` / `XlsxTabularReader` 输出统一
  `TabularRow(row_number, sheet_name, raw_payload)`；正式 ImportSession 支持
  `.csv` 与 `.xlsx`，不要求用户转 CSV；同一文件 hash 复用既有 ImportSession
  （`uq_import_sessions_source_hash`），无独立 XlsxImportSession。
- **联系人继承**：合并单元格证据下，联系人行继承锚点公司身份
  （`inherited_company_source_row`、`grouping_rule`、`grouping_confidence`、
  `inherited_fields`），不复制不存在的公司事实；无合并证据 → 不 forward-fill，
  标记 `company_review_required`。
- **Mapping aliases**：新增 联系人邮箱/联系人职位/公司官网/供应商等别名；
  置信度改为 exact known alias → HIGH、fuzzy（表头包含别名）→ MEDIUM。
- **Evidence 语义**：有摘要贸易字段（HS/产品/供应商/金额）且无逐票字段的行
  标记 `record_kind=company_import_summary`；金额保存 `import_value_raw`，
  无明确币种时 `currency=unknown`（`$` 不假定 USD）；**不生成 fake shipment /
  fake shipment_date / fake supplier transaction**。
- **不映射字段**（保留 Raw）：是否中国进口、中国/总进口次数、联系人级别、
  保存时间、最后进口时间。
- **前端**：Mapping 页面默认表格（字段→系统字段→Confidence + dropdown，
  JSON 保留在高级设置）；显示“公司进口摘要，不代表单票海运记录”与
  “本步骤不会发送邮件”；正式导入按钮接受 CSV/XLSX。

## 3. Preflight V2（只读，真实文件）

| 指标 | 值 |
| --- | --- |
| rows | 127 |
| company anchor rows | 55 |
| contact rows | 72 |
| linked_contact_rows | 72 |
| orphan_contact_rows | 0 |
| invalid_rows | 0 |
| unique companies（estimate） | 53 |
| unique contacts（by name） | 111 |
| company duplicate groups | 2 |
| email duplicate groups | 4 |
| company_import_summary rows | 55 |
| true shipment rows | 0 |

Mapping（自动，仍须人工确认）：HIGH=company_name、website、contact_name、
contact_email、contact_title、hs_code、supplier；MEDIUM=amount、
product_description、country；UNMAPPED=是否中国进口、中国/总进口次数、
最后进口时间、联系人级别、保存时间。

## 4. 测试结果

| 门禁 | 结果 |
| --- | --- |
| 新增单元测试（XLSX 解析/合并继承/孤儿/重复/摘要/币种/别名） | 通过 |
| CSV intake 回归 + domain | 通过 |
| PostgreSQL 集成（XLSX 上传幂等 + 继承持久化 + 既有 CSV 集成） | 通过（6） |
| Ruff（改动文件） | 通过 |
| strict mypy（改动文件） | 通过 |
| Alembic check / heads | 无 drift，单 head `d5d2b1c2d3e4`（无新增 Migration） |
| Frontend tsc / ESLint / production build | 通过（0 error，5 既有 warning） |
| 定向 Playwright（bulk-import + runtime-health + acceptance-ux） | 14/14 通过 |

测试覆盖：CSV import regression、XLSX import、merged-cell/company-group、
contact-only continuation、orphan contact、duplicate company、duplicate email、
company summary evidence、no fake shipment、unknown currency、mapping aliases、
same XLSX re-upload idempotency。

## 5. Accepted technical debt

- **ACCEPTED DEBT 1**：XLSX 使用 bounded chunk/batch parse（zipfile + XML 全量
  读入内存），尚非真正 streaming。原因：当前目标 ≤20k 行，MVP 成本收益不支持
  现在引入流式 ETL。
- **ACCEPTED DEBT 2**：`company_import_summary` 暂以 raw payload 元数据形式
  复用现有 Evidence boundary，未建立完整海关 summary 数据仓库。原因：先验证
  Routing/销售价值。
- 无新增无理由技术债；未修改历史 Migration；未为匹配 production 修改 ORM。

## 6. 合规

- 未写数据库（Preflight/测试均在本地/隔离环境；生产库未触碰）。
- 未调用真实 Provider/LLM/Umail；未发送邮件。
- 真实联系人邮箱未进入测试日志/报告（本报告只有统计与脱敏样例）。

## 7. Blocker / Next user action

正式导入前仍需用户在 UI 完成：确认 Mapping → 勾选“我确认这是我拥有或有权
处理的真实业务数据” → 点击“开始正式导入”。Codex 不代替用户点击。
