# D5e2f.2 Routing Exclusion Semantic Hardening + Human Review Readiness 报告

日期：2026-08-07

## 最终状态

**READY_FOR_LEO_FINAL_ENTITY_REVIEW** —— taxonomy 修复后 D 全部具备显式证据、
unknown 不再误入 D；Routing Apply 未执行。Leo 需完成 10 条 entity review 后
确认 Preview。

## 1. Before / After 分布（生产 52 家）

| Tier | v1.1（修复前） | v1.1 + fitness_equipment_v1（修复后） |
| --- | --- | --- |
| A | 0 | **2**（TUFF TORQ 94.0；PURSUE MOVEMENT 76.5） |
| B | 2 | **1**（LION HEART GYM 68.5） |
| C | 0 | **39**（全部 TARGET_RELEVANCE_UNKNOWN） |
| D | 48 | **8**（全部 EXPLICIT_* 证据） |
| blocked | 2 | 2（FULFLEX、PRO PAK，ENTITY_REVIEW_PENDING） |

## 2. 48 旧 D 审计

- 原 48 个 D 均为“product/HS 与 fitness 目标零匹配 → NON_TARGET_INDUSTRY”。
- 修复后归因：**8 个真实显式 non-target**（BEST SP、CNH UK、STREAMLINE
  PACKAGING、BURLINGTON、THE J M SMUCKER、BEAUTY SYSTEMS、DY CONCRETE PUMPS、
  EN POINTE；产品/HS 命中 explicit taxonomy）；**39 个 taxonomy-unknown**
  （无匹配且无显式证据 → C）；**1 个 fitness target 被旧规则误 D**
  （TUFF TORQ，现 A，PRODUCT_HS_MATCH_FULL + FITNESS_EQUIPMENT_SIGNAL）。
- D 检查：8/8 至少一个 EXPLICIT_* reason（EXPLICIT_NON_TARGET_PRODUCT /
  EXPLICIT_NON_TARGET_HS），无 missing-field 类 D。

## 3. Taxonomy 技术选择

`TargetTaxonomyConfig`（版本化，无 ML/LLM）：target keywords/aliases、target
HS prefixes、explicit non-target categories、explicit non-target HS groups；
`fitness_equipment_v1`。选择原因：① 真实标签不足；② 必须可解释；③ 零 API
成本；④ 可随真实开发结果快速迭代；⑤ 后续可替换 learned ranking。技术债：
taxonomy 需人工维护（MVP 阶段可控，优于未校准 ML/LLM）。

## 4. 语义与 reason codes

- TARGET_MATCH（TARGET_PRODUCT_MATCH / TARGET_HS_MATCH / FITNESS_EQUIPMENT_SIGNAL）
  ≠ EXPLICIT_NON_TARGET（EXPLICIT_NON_TARGET_PRODUCT / EXPLICIT_NON_TARGET_HS）；
- 零匹配且无显式证据 → TARGET_RELEVANCE_UNKNOWN + PRODUCT/HS_TAXONOMY_UNMATCHED
  → **C（不得 D，也不得被其他信号提升到 A/B）**；
- D 仅显式排除：SUPPRESSED / FREIGHT_FORWARDER / CUSTOMS_BROKER /
  LOGISTICS_PROVIDER / NON_US_TARGET / INVALID_COMPANY / CLEAR_DATA_CONFLICT /
  USER_EXCLUDED / NON_TARGET_INDUSTRY（仅显式证据）。

## 5. B 公司非硬编码

PURSUE MOVEMENT / LION HEART GYM 的 tier 来自通用规则（TARGET_PRODUCT/HS_MATCH）；
回归测试：删除/替换 company_name 后相同事实仍得相同 tier。

## 6. blocked

FULFLEX、PRO PAK 保持 blocked（ENTITY_REVIEW_PENDING），未绕过。

## 7. 测试

15 passed（taxonomy 语义、zero-match≠D、unknown→C、explicit→D、missing
HS/product→非 D、high-score unknown 仍 C、department 安全、blocked 保持、
determinism、B 非名称硬编码、rules version）；Ruff / strict mypy 通过；
v1/v1.1 既有路由测试通过。

## 8. 合规

ProspectRoute=0 · Opportunity=0 · Research 未执行 · LLM/Provider 未调用 ·
Umail 未导出 · 邮件未发送。

## 9. Technical debt

taxonomy 人工维护；ML ranking / learned weights / conversion model / Umail
API / streaming parser / Employment History / external company identity ——
均因暂无真实开发结果标签而延期。

## 10. Remaining blockers（Human Review UX / Apply gate）

1. Leo 完成 10 条 entity review（Review Card 默认 DEFER；MERGE/KEEP_SEPARATE/
   DEFER）；
2. Routing Review UI（A/B/C/D/blocked 数量 + 每公司 Tier/Score/Positive/
   Negative/Unknown/reasons + “Tier 不是成交概率”）与 Apply gate
   （entity pending=0 且 preview valid 才 Enable）本轮未接入前端，待实现；
3. 确认后授权 Apply（A 类 ≤5 家/批）。
