# D5e2f Human Entity Review + Real Routing Preflight 报告

日期：2026-08-07

## 最终状态

**READY_FOR_REAL_ROUTING_APPLY（暂定）** —— deterministic Routing Preview 已生成；
真实 Apply 前须由 Leo 完成 10 条 pending entity review（UI 默认 DEFER）并确认
Preview。Routing 未执行。

## 1. Production counts（review 前，生产实测）

ImportSession 1 · RawImportRow 127 · Company 52 · Contact 118 · CompanyContact
113 · ImportEntityDecision 250（pending 10）· ProspectRoute 0 · Opportunity 0 ·
Draft 0 · department company_contacts 12。

## 2. 55 → 52 归并 Provenance（精确）

55 个锚点行的决策分布：

- **auto_create：52 个锚点** → 各自创建 1 个 canonical company（52 家）；
- **auto_merge：2 个锚点**（rows 51、58）→ 按同域名+同名称 HIGH 并入既有
  canonical：
  - Cluster `7f0cbbe0`：rows 49（create）+ 51（merge）→ “MPI PRODUCTS
    DEEFIELD WISCONSIN LLC”（mpiproducts.com）2→1；
  - Cluster `6695fa25`：rows 56（create）+ 58（merge）→ “CEVIANS LLC 录入线索”
    （cevians.com）2→1；
- **review_required：1 个锚点**（row 79 “STAK INDUSTRIES INC.”→ candidate
  `10850329` PRO PAK，`company_name_similar`，conf 0.79）——未合并，pending；
  其余 4 条 company_name_similar 决策为续行（非锚点）。

结论：55 = 52 create + 2 merge + 1 review-anchor ⇒ canonical 52。
**修正 D5e2e1 报告**：此前“2 组归并 + matcher normalization 导致 53/52”表述
不完整；实际为 2 组 2→1 HIGH 归并 + 1 个 review 锚点（未并）+ 52 create。

## 3. Pending decisions（10）

- 5 Company `company_name_similar`（含锚点 row 79 STAK→PRO PAK；conf 0.55–0.79）；
- 5 Contact `same_company_name_only`（conf 0.55）；
- UI Review Card 默认 **DEFER**（PR #20：新增“推迟（DEFER）”默认项），操作
  MERGE / KEEP_SEPARATE / DEFER；不默认 Merge；
- Leo 尚未代决（reviewed=0）；review 持久化由后端现有
  decision/reviewed_by/reviewed_at/reason_codes/candidate 链路保证，非前端
  local state。

## 4. Department contact safety

12 个共享邮箱（admin/info/purchase/purchasing/sales/support 等）已落
`is_department_contact=true`，保留 Contact 与 CompanyContact；PR #17 保证
**永不自动成为 Decision Maker**；新增 parametrized 回归测试
（info/sales/support/admin/office/hello：标记+保留+角色 UNKNOWN）通过。

## 5. Company external identity

真实 XLSX 无 NetEase company ID / external company ID / stable source
identifier 列（`company_external_identities=0`，preflight coverage 0%）→
记录 **NOT_AVAILABLE_IN_SOURCE**；未用生成 ID 冒充 source ID。

## 6. Routing Pre-Score（deterministic，只读）

- rules_version：**real-routing-v1**；
- 输入：canonical Company + Raw summary 字段（产品/HS/供应商/金额/国家/最后
  进口时间）+ CompanyContact（联系人角色/邮箱）；**无 Research、无 LLM、
  无 Provider**；
- 权重：`DEFAULT_WEIGHTS`（scorer 集中配置，版本化）：product_or_hs_match 30、
  import_recency 20、import_frequency 15、origin_country_match 10、port_match
  10、contact_quality 10、data_completeness 5；
- 语义：company_import_summary ≠ shipment；无逐票证据 → `IMPORT_RECENCY_NONE`、
  `SHIPMENT_DATE_MISSING`，不生成虚假频率/次数/体积。

## 7. Routing Preview（真实数据，52 家）

| Tier | count |
| --- | --- |
| A | 0 |
| B | 0 |
| C | 0 |
| D | 50 |
| blocked | 2（FULFLEX、PRO PAK —— pending entity review，`ENTITY_REVIEW_PENDING`） |

- 每家公司：pre_score（5.2–18.4）、top reasons
  （`PRODUCT_HS_MATCH_*`、`IMPORT_RECENCY_NONE`、`IMPORT_FREQUENCY_PARTIAL`）、
  contact count、best contact role、data completeness；
- 同输入 + real-routing-v1 → 同结果（确定性，脚本两次输出一致）；
- A=0 如实报告：无真实逐票 shipment 证据时按规则不升 A/B。

## 8. 合规

Opportunity=0（PreScore 未污染）；Research 未执行；LLM/外部 Provider 未调用；
Umail 未导出；邮件未发送；ProspectRoute=0（未 Apply）。

## 9. Technical debt

同前（chunk/batch parser、Employment History、fuzzy ML、Umail API、自动邮件、
分布式队列）；新增：Routing Preview 的只读页面面板尚未接入 UI（本轮以只读脚本
计算并输出数字，Step 5 Apply 面板在真实 Apply 时渲染）。

## 10. Remaining blockers

1. Leo 在 Step 4 完成 10 条 review（默认 DEFER；批准则按规则 merge/keep）；
2. Leo 确认 Routing Preview 后授权 Apply（A 类按 ≤5 家/批；B 类仅 Preview）。
