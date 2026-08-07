# D5e2f.1 Real Routing Calibration Before Apply 报告

日期：2026-08-07

## 最终状态

**ROUTING_PREVIEW_BLOCKED** —— v1.1 校准策略已实现并通过本地测试；生产 v1.1
Preview 数字待部署后生成（GitHub/Zeabur 网络当前不可达，推送/合并/部署被阻塞）；
另有 10 条 Leo entity review 待完成。未执行任何 Routing Apply。

## 1. Old real-routing-v1 分布与根因

生产真实 Preview（real-routing-v1）：

| Tier | count |
| --- | --- |
| A | 0 |
| B | 0 |
| C | 0 |
| D | 50 |
| blocked | 2（ENTITY_REVIEW_PENDING） |

reason_code 命中（v1 运行统计）：`PRODUCT_HS_MATCH_PARTIAL`/`_NONE`、
`IMPORT_RECENCY_NONE`、`IMPORT_FREQUENCY_PARTIAL` 为主。

**50×D 根因**：v1 为 100 分满分相加，missing recency（无逐票 shipment）给 0 分、
frequency 仅按 source_row_count 计、relevance 稀疏，最终 pre_score 5–18.4；
`recommend_prospect_tier` 把低分映射为 D。即 **missing recency 通过低分间接把
公司打入 D**，违反 “UNKNOWN != NEGATIVE”。

## 2. Source fact inventory（真实 52 家 Canonical）

| 字段 | 覆盖 | source / 语义 |
| --- | --- | --- |
| company_name | 52/52 | canonical name |
| website/domain | 52/52（有 domain） | 合法性信号 |
| country | 55 行 summary（公司级） | 国家/地区（US 目标） |
| product_description | 55 行 summary | 主要进口产品（真实 source fact） |
| hs_code | 55 行 summary | HS Code（真实 source fact） |
| import_amount | 55 行 summary | 进口金额（raw，币种 unknown） |
| last_import_at | 55 行 summary | 最后进口时间（真实 source fact） |
| supplier | 55 行 summary | 最大供应商 |
| contact / company_contact | 113 关系 | 联系人覆盖 |
| personal email | 除 12 部门邮箱外 | 自然人邮箱 |
| department email | 12 | is_department_contact=true |

55 条为 company_import_summary（≠ shipment）；不虚构 shipment_count /
frequency / volume / recency，但 summary 中的真实字段可直接用作 source fact。

## 3. real-routing-v1.1 规则（新增，未改 v1）

- rules_version：`real-routing-v1.1`（集中配置 V11_WEIGHTS / V11_TIER_*）；
- additive 维度与权重：importer_source_confidence 20 · product_hs_relevance
  25（产品 60%/HS 40%）· import_value_signal 15 · website_legitimacy 10 ·
  contact_coverage 15 · person_contact_quality 10 · data_completeness 5；
- **Missing = 0，不扣分**；warnings（IMPORT_RECENCY_UNKNOWN、
  IMPORT_VALUE_UNKNOWN、PRODUCT/HS_DATA_MISSING、PERSON_CONTACT_MISSING）；
- D 仅显式排除：SUPPRESSED / FREIGHT_FORWARDER / CUSTOMS_BROKER /
  LOGISTICS_PROVIDER / NON_TARGET_INDUSTRY / INVALID_COMPANY / NON_US_TARGET /
  CLEAR_DATA_CONFLICT / USER_EXCLUDED；禁止
  NO_IMPORT_RECENCY/NO_SHIPMENT_COUNT/NO_PHONE/NO_LINKEDIN/MISSING_ADDRESS 入 D；
- 阈值：A≥70 · B 45–69 · C 20–44（<20 归 C + INFO_INSUFFICIENT）· D=exclusion ·
  blocked=未解决冲突（pending review）；
- 联系人信号：person email（+title/preferred role）质量分；department 邮箱仅
  弱可触达（+2），永不自动成为 Decision Maker；不要求 LinkedIn；
- 产品/HS：deterministic keyword/prefix 匹配（含 fitness 关键词与 HS 前缀
  9506/950691/950699），reason：TARGET_PRODUCT_MATCH /
  TARGET_HS_MATCH / FITNESS_EQUIPMENT_SIGNAL；
- import amount：parse/normalize/validate → 强度 band（≥250k 15 / ≥50k 10 /
  >0 5），记录 source field，非成交概率；
- sanity gate：>80% D 且主要来自 missing codes → ROUTING_PREVIEW_INVALID；
  A+B=0 但存在 target product + valid company + valid email/contact →
  ROUTING_PREVIEW_INVALID（异常检测，不强制比例）。

## 4. 单元验证（35 passed）

- missing recency/value → 不 D、不扣分（pre_score>0，warnings 标注 unknown）；
- valid target + missing recency → 非 D（score≥45，FITNESS_EQUIPMENT_SIGNAL +
  IMPORT_VALUE_SIGNAL）；
- explicit forwarder exclusion → D（FREIGHT_FORWARDER）；
- department 邮箱 → 弱信号，非 D，不成为 Decision Maker；
- determinism + rules_version 断言；
- v1 回归（test_prospect_routing 等）全部通过。

## 5. 生产 v1.1 Preview

**待部署后执行**（网络阻塞）：将用当前 52 家真实 canonical 公司 + real-routing-v1.1
重新输出 A/B/C/D/blocked 并与 v1 对比；不得为凑 A/B 数量调规则。

## 6. 合规

ProspectRoute=0 · Opportunity=0 · Research 未执行 · LLM/Provider 未调用 ·
Umail 未导出 · 邮件未发送。

## 7. Technical debt

ML ranking、learned weights、historical conversion model、Umail API、streaming
parser、完整 Employment History、外部 company identity enrichment —— 均因暂无
真实开发结果标签而延期，Rule-based v1.1 适合首次 MVP 验证。

## 8. Remaining blockers

1. GitHub/Zeabur 网络不可达：v1.1 代码推送、PR、合并、生产部署未完成；
2. 生产 v1.1 Preview 数字待生成；
3. Leo 完成 10 条 entity review 后确认 Preview，才可 Apply（A 类 ≤5 家/批）。
