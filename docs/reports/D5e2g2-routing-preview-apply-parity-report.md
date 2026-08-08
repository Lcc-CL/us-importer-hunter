# D5e2g.2 — Routing Preview / Apply Semantic Parity Gate

## 结论

**SAFE_FOR_LEO_ROUTING_REVIEW**

Preview 与 Apply 已收敛到同一个 evaluator（`RoutingPolicyV11`）、同一 taxonomy
（`fitness_equipment_v1`）、同一 rules_version（`real-routing-v1.1`），同一份数据
产生的 tier / score / reason_codes / blocked 在两条路径完全一致（PostgreSQL 集成
Parity 测试逐字段验证）。Country 语义已修复：`NON_US_TARGET` 只依据进口商公司
所在国，货物/供应商来源国（如 China）不再触发排除。本轮**没有执行任何真实 Routing
Apply**，停在 Leo 完成 9 条 Entity Review + 第一次真实 Routing Apply 之前。

---

## 1. 修复前 Preview / Apply 调用链

### Preview（只读）

`POST /import-sessions/{id}/routing-preview`
→ `ProspectRoutingQueryWorkflow.routing_preview`
→ `RoutingFeatureProjector.project(source, mapping)`
→ `RoutingPolicyV11.evaluate(criteria, features, taxonomy=fitness_equipment_v1())`
→ 返回 `tier / pre_score / reason_codes / blocked / rules_version=real-routing-v1.1`

### Apply（持久化）

`POST /import-sessions/{id}/routing-runs`（创建 run，rules_version=
`d5c-deterministic-routing-v1`）
→ 后台 `ProspectRoutingExecutionWorkflow.execute`
→ `RoutingFeatureProjector.project(source, mapping)`
→ `DeterministicProspectRoutingScorer.score(...)`（**legacy evaluator**）
→ `ProspectRoute.create(...)` → 持久化 `prospect_routes`

### 两条链路的差异（根因）

| 维度 | Preview | Apply |
| --- | --- | --- |
| evaluator | `RoutingPolicyV11` | `DeterministicProspectRoutingScorer`（legacy） |
| rules_version | `real-routing-v1.1` | `d5c-deterministic-routing-v1` |
| weights | `V11_WEIGHTS` | `DEFAULT_WEIGHTS`（legacy） |
| taxonomy | `fitness_equipment_v1` | 不使用 taxonomy |
| 硬排除字段 | `origin_countries` → `NON_US_TARGET` | 无 `NON_US_TARGET`（用 `EXPLICIT_TARGET_MISMATCH`） |
| tier 阈值 | A≥70 / B≥45 / C≥20 / D=显式排除 | A≥75+contact / B≥50+email / C≥30 |
| reason codes | `TARGET_A_CANDIDATE` 等 | `ROUTED_A` 等 |
| blocked 表示 | pending 公司直接 `ENTITY_REVIEW_PENDING`（不跑 evaluator） | `UNRESOLVED_COMPANY_CONFLICT_BLOCKED`（跑 evaluator） |

结果：同一家公司 Preview 显示 A/B/C，Apply 可能写入不同的 tier/score/reason；这是
D5e2g.1 审计确认的 P0 blocker。

---

## 2. 根因

1. **两个 evaluator**：D5e2f 新增 `RoutingPolicyV11` 只接入了 Preview，Apply 仍走
   legacy scorer，两套规则并行。
2. **Country 语义混淆**：v1.1 的 `_hard_exclusion` 用 `features.origin_countries`
   判断 `NON_US_TARGET`，而 `origin_countries` 来自逻辑字段 `origin_country`
   （真实网易文件里没有映射；若有「来源国/原产国」列则会被当作进口商国家）。
   产品语义上它是**货物/供应商来源国**，不是进口商所在国。美国进口商从中国进口
   会被错误判 D。
3. **Preview 截断与短路**：`reason_codes[:8]` 截断；pending 公司不跑 evaluator，
   导致 blocked 公司的 reason/pre_score 与 Apply 不一致。

---

## 3. Country Domain Semantic（修复后）

两个字段语义严格区分：

| 逻辑字段 | 中文语义 | Domain 字段 | 用途 |
| --- | --- | --- | --- |
| `country` | 进口商所在国家/地区 | `RoutingFeatureInput.importer_country` | `NON_US_TARGET` 唯一依据；未知 → `IMPORTER_COUNTRY_UNKNOWN`（C，不 D） |
| `origin_country` | 产品/供应商来源国 | `RoutingFeatureInput.origin_countries` | 仅 source-fact 完整性 / origin 匹配；**永不触发排除** |

真实生产映射验证（只读 `GET /import-sessions/{session}`）：

```json
"logical_fields": { ..., "country": "国家/地区", ... }
```

生产文件没有映射 `origin_country`；`国家/地区` 的实际值分布（250 条决策行）：

| 值 | 行数 |
| --- | --- |
| 美国 | 82 |
| 加拿大 | 28 |
| 缺失 | 140 |

因此修复后，加拿大进口商将按显式 `NON_US_TARGET` 进入 D（符合“explicit non-US
importer 可以进入 D”），美国进口商不受影响，缺失国家为 unknown（不 D）。

Mapping UI 标签同步区分：

- `country` → 「进口商所在国家/地区 / Importer company country」
- `origin_country` → 「产品/供应商来源国 / Shipment/Supplier origin country」

---

## 4. 修复后的 Single Evaluator

`RoutingPolicyV11` 成为唯一 evaluator：

```text
evaluate(criteria, features, taxonomy) -> RoutingScoreResult
    ↑                        ↑
RoutingPreview        RoutingApply (score_route -> ProspectRoute.create)
（只读展示）            （同一决策后持久化）
```

变更点：

- `RoutingFeatureInput` 新增 `importer_country`（默认空 = UNKNOWN）。
- `RoutingFeatureProjector` 从映射字段 `country` 填充 `importer_country`；
  `ROUTING_FIELD_ALIASES` 增加 `country` 别名。
- `RoutingPolicyV11._hard_exclusion`：`NON_US_TARGET` 只检查 `importer_country`；
  unknown → `IMPORTER_COUNTRY_UNKNOWN` warning，不排除。
- `RoutingPolicyV11.score_route(...)`：Apply 唯一入口，包装 `evaluate` 后持久化
  `ProspectRoute`。
- `ProspectRoutingExecutionWorkflow` 改用 `RoutingPolicyV11.score_route` +
  `fitness_equipment_v1()`。
- 路由 run 的 `rules_version` = `real-routing-v1.1`，`weights_snapshot` = `V11_WEIGHTS`
  （run 创建与 configuration hash 同步）。
- Preview：对所有公司（含 pending）跑同一 evaluator；blocked 公司 reason =
  `UNRESOLVED_COMPANY_CONFLICT_BLOCKED`（与 Apply 一致）；reason_codes 不再截断；
  `explicit_negative` 补充展示 `NON_US_TARGET` 等硬排除。
- 无新数据库、无新队列、无 ML/LLM；未新增 Migration（`importer_country` 为计算字段）。

---

## 5. 52 家 real-data parity 结果

### 修复前生产 Preview（只读快照，`real-routing-v1.1`）

```text
A=2 · B=1 · C=39 · D=8 · blocked=2（52 家；entity_pending_count=9）
```

修复前 Apply evaluator（legacy）与 Preview 不一致（§1 表），无法逐家对齐。

### 修复后（单 evaluator）

同一份数据 Preview == would-apply，由构造保证：

- 两条路径调用同一个 `RoutingPolicyV11.evaluate`；
- 集成 Parity 测试逐字段断言 `preview tier == persisted recommended_tier`、
  `preview pre_score == persisted pre_score`、
  `preview reason_codes == persisted reason_codes`、
  `rules_version == real-routing-v1.1`、blocked 一致；
- 生产只读 Preview 快照（部署后）与 Apply 唯一差异是 Apply 未执行。

### 部署后生产 Preview 快照（只读）

部署后（`e5c988e`，`rules_version=real-routing-v1.1`，`preview_valid=True`，
`entity_pending_count=9`，52 家）：

```text
修复前：A=2 · B=1 · C=39 · D=8 · blocked=2
修复后：A=2 · B=1 · C=27 · D=20 · blocked=2
```

变化全部由 Country 语义修复驱动：

- **A/B 不变**：TUFF TORQ（A 93.95）、PURSUE MOVEMENT（A 76.45）、
  LION HEART GYM（B 68.45）——美国进口商 + 中国来源国不再被误排除，继续 A/B。
- **12 家 C → D**：ACCELERATED SYSTEMS、ENCOM WIRELESS、RADIANT TECHNOLOGIES、
  WEISHAUPT、MATRIX ELECTRONICS、JOBAL MANUFACTURING、MANLUK INDUSTRIES、
  OCEAN CHOICE INTERNATIONAL、PREMIER PERFORMANCE CANADA、SOREL FORGE、
  SUN RICH FRESH FOODS、VITA HEALTH PRODUCTS——均为 `国家/地区=加拿大`
  的显式非美国进口商，新增 `NON_US_TARGET`（explicit non-US importer → D，
  符合任务语义；这不是缺值惩罚）。
- **1 家原有 D 叠加 NON_US_TARGET**：EN POINTE ENTERPRISES LTD.（加拿大 + 显式
  非目标行业），tier 不变（D），reason_codes 增加 `NON_US_TARGET`。
- **blocked 两家现在有真实 evaluator 输出**：FULFLEX（pre_score 52.74）、
  PRO PAK（68.95），reason 含 `UNRESOLVED_COMPANY_CONFLICT_BLOCKED`——与 Apply
  会持久化的路由完全一致（此前 preview 只返回 `ENTITY_REVIEW_PENDING`/0.0）。
- **未知国家（140 行缺失）未进入 D**：全部保持 C（unknown，不惩罚）。
- 其余 27 家 C 与原有显式非目标 D（BEAUTY SYSTEMS、BEST SP、BURLINGTON、
  CNH UK、DY CONCRETE PUMPS、STREAMLINE PACKAGING、THE J M SMUCKER 等）逐家
  tier/score/reason 与修复前一致。

52 家逐家比对：仅以上 14 家发生 tier/score 变化（12 家 C→D + 2 家 blocked 的
pre_score 从 0.0 变为真实值）；其余 38 家完全一致。`company_id` 集合前后一致
（52 = 52）。

---

## 6. 是否 DIFF = 0

**是。** Preview 与 Apply 使用同一 evaluator 后，对同一公司同一输入：

- tier：一致（blocked ↔ `review_status=blocked` / `recommended_tier=None`）
- score：一致
- reason_codes：一致（集合相等；含 blocked 的 `UNRESOLVED_COMPANY_CONFLICT_BLOCKED`）
- blocked：一致
- rules_version：一致（`real-routing-v1.1`）

由 `test_routing_preview_apply_parity.py` 在真实 PostgreSQL 上逐家公司验证。

---

## 7. 测试

| 门禁 | 结果 |
| --- | --- |
| `uv run pytest`（后端全部，含 PostgreSQL 集成） | **1258 passed** |
| `uv run ruff check .` | 通过 |
| `uv run mypy app tests --strict` | 通过（431 文件） |
| `uv run alembic heads` | 单 head `d5d2b1c2d3e4`，无新增 Migration |
| 前端 `tsc --noEmit` / `npm run lint` / `npm run build` | 通过 |
| Playwright：bulk-import / routing-batch-start / umail-export-suppression | **3 passed** |

新增 Parity / Country 语义测试（覆盖任务清单 1–14）：

1. preview decision == apply decision → `test_preview_and_apply_produce_identical_decisions`
2. preview tier == persisted tier → 同上
3. preview score == persisted score → 同上
4. preview reason_codes == persisted reason_codes → 同上
5. preview rules_version == persisted rules_version → 同上
6. blocked company 无法 Apply → `test_pending_entity_review_blocks_apply_and_blocked_route_cannot_batch`
7. pending Entity Review > 0 时 Apply blocked → 同上（preview `entity_pending_count=1`，blocked 路由 409）
8. US importer + China origin 不得因 origin_country 判 NON_US_TARGET → 单元
   `test_us_importer_with_china_origin_is_never_non_us_target` + Parity 集成
9. explicit non-US importer 可以进入 D → `test_explicit_non_us_importer_is_d`
10. unknown importer country 不允许缺值直接进 D → `test_unknown_importer_country_is_c_not_d`
11. taxonomy unknown → C → `test_unknown_taxonomy_is_c_not_d` / `test_no_target_match_is_not_d`
12. explicit non-target product → D → `test_explicit_non_target_product_is_d`
13. department mailbox 不影响公司国别判断 → `test_department_mailbox_does_not_change_country_judgment`
14. 同一数据重复 Preview deterministic → `test_preview_is_deterministic` + Parity 集成二次 Preview

---

## 8. 部署

- PR → Squash Merge → main
- Zeabur Backend / Worker / Frontend 自动部署
- 生产只读 smoke：health、runtime、Preview 快照、pending=9
- **未执行任何真实 Routing Apply / Research / LLM / Umail / 邮件**

---

## 9. 技术债

1. **Persistent Entity Pair Exclusion（P1）**：REJECT 只影响当前 session；重新导入
   仍可能再次提出同一候选。本轮明确不实现，仅记录。REJECT tooltip 已注明：
   「仅拒绝本次导入中的候选匹配关系，不删除任何数据；重新导入时未来仍可能再次出现。」
2. **Legacy scorer 保留但不再被 Apply 使用**：`DeterministicProspectRoutingScorer`
   与其 `d5c-deterministic-routing-v1` 常量保留供历史数据/回滚参考；下一轮可清理。
3. **i18n.spec.ts 2 个 legacy manual-form 用例**：在 main 上同样失败（旧入口收敛），
   与本轮无关，记录为 Issue，不做扩大重构。
4. **Preview 分数与既有生产 run 的历史不一致**：修复后新 run 的 rules_version 变为
   v1.1；历史 run 仍保留旧版本快照（`execution_generation` 机制兼容）。
5. **ML ranking / learned weights / historical conversion model**：仍无真实开发结果
   作为训练标签，规则化 v1.1 继续作为首次 MVP 验证基线。

---

## 10. 下一步 Leo 应执行什么

1. 在 Step 4 完成剩余 **9 条 Entity Review**（暂缓/合并/分离/拒绝此候选关系）。
2. 全部 pending 解除后，Step 5 生成 Routing Preview（此时 preview 与 apply 同规则）。
3. 人工确认 Preview 的 A/B/C/D 分布（可接受变化，见 §5）。
4. 启用真实数据开关并点击「确认应用 Routing」——**这一步必须由 Leo 执行**，
   本系统/本轮不会自动 Apply、不会发邮件。
