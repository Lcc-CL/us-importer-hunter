# D5e2h1 — Canonical Routing Count Integrity + Step 5 UI State Repair

## 结论

Routing 的 55 个候选是**正确结果**，不是重复评分：125 条有效行的 company
decisions 归并到 **55 个不同的 Canonical Company**（此前 D5e2g.2 的 52 是人工
Review 前的状态；Leo 的 3 条 company `keep_separate` 各自新建了 1 家公司 →
52 + 3 = 55）。A+B+C+D+blocked = 55 = routing candidate count = canonical
company count，Count Invariant 成立，无重复 canonical company。本轮修复的是
**顶部统计语义、stage-aware 提示与 stale error 状态**，未改评分算法。

未执行任何真实 Routing Apply / Research / LLM / Umail / 邮件。

---

## 1. 127 → 125 → 55 → 52 的准确业务含义

生产 ImportSession `2850767c-…` 只读审计（250 条 decision，3 页取全）：

```text
127  raw rows（原始行，含 2 行无效）
 → 125 accepted rows（有效行）
 → 125 company decisions + 125 contact decisions（每行一条 company + 一条 contact 决策）
 → 55 个 distinct canonical company candidates（candidate_entity_id 去重，
    decision != rejected）
 → Routing Preview 55 家公司（A=2 · B=1 · C=31 · D=21 · blocked=0）
```

company decisions 构成：

| decision | 数量 | 说明 |
| --- | --- | --- |
| auto_create | 52 | 新建 52 家 canonical company |
| auto_merge | 68 | 复用已有 candidate（anchor 归并，不新增） |
| manual_merge（Leo） | 2 | 人工合并到已有 candidate |
| keep_separate（Leo） | 3 | 各自新建 1 家 canonical company |

55 = 52（auto_create）+ 3（keep_separate 新建）。`52` 是 D5e2g.2 部署时（9 条
Review 未决）的数字；人工 Review 完成后为 55，属预期业务进展。

## 2. Routing 修复前为什么是 55

不是 bug：`list_source_companies` 以 **company decision 的 candidate_entity_id
去重**为业务主键（即 Canonical Company ID），125 条 company decision → 55 个
不同 candidate。preview 与 apply 同源（D5e2g.2 单 evaluator），因此 55 就是
“Entity Resolution 后唯一 canonical company 且 eligible for routing”的数量。
顶部 UI 的「Company 125」来自 `companies_created + companies_reused`
（**每行一条 company decision 的计数**），混淆了 raw/decision/canonical 概念。

## 3. 修复后 canonical routing count

55（与修复前一致——因为 routing 计数本来就正确）。

## 4. A/B/C/D/blocked 新计数

生产只读 Preview（D5e2h1 preset 参数，pending=0）：

```text
A=2 · B=1 · C=31 · D=21 · blocked=0，合计 55 = canonical company count
preview_valid=True · rules=real-routing-v1.1
```

## 5. 是否存在重复 canonical company

**不存在。** 55 = 125 条 company decision 中 distinct `candidate_entity_id` 的
个数；每个 id 对应 companies 表一行（`candidate_entity_id` 为外键）。多行 anchor
merge 到同一公司时只出现一次（68 条 auto_merge + 2 条 manual_merge 全部去重）。
集成测试 `test_keep_separate_adds_one_canonical_company_and_routing_counts_match`
证明：KEEP_SEPARATE 后 canonical 4→5、preview 也恰好 5，两个同名 anchor 各自
出现一次，无重复评分。

## 6. stale red error 根因

Step 5 页面顶部红色 banner 来自面板**单一全局 `error` state**：

- 后台轮询（rows/resolution/routing/batch 的 interval）失败时直接 `setError(...)`
  （`bulk-import-panel.tsx` 轮询 catch 分支）；
- 轮询成功不会清除旧的 `error`（部分轮询只有 `.catch`，无成功清空）；
- 非 ApiError 的异常走 `getClientErrorDetails` fallback：
  `"Something unexpected happened while processing the request."`。

修复：

- 轮询失败改为 scoped `pollError`（独立小 banner，成功即清除），不再污染全局；
- 全局 `error` 仅由用户主动 action 使用，action 开始时清除；
- fallback 错误码 `unexpected_client_error` 映射为中文
  「发生意外错误，请稍后重试。」；新增 `ROUTING_TARGET_REQUIRED` 等业务映射；
- 成功 Preview 后全局 error banner 不可见（e2e 断言 `global-error` 不可见）。

## 7. 顶部统计修改前后

| 修改前（混淆 raw/decision/canonical） | 修改后（业务语义，全部来自 API） |
| --- | --- |
| Raw {total_rows} | 原始行 {session.total_rows} |
| Company {companies_created+reused} | 有效行 {session.accepted_rows} |
| Contact {contacts_created+reused} | Canonical 公司 {resolution.canonical_company_count} |
| Route {routingRun.total_companies} | Canonical 联系人 {resolution.canonical_contact_count} |
| | 已生成优先级 {preview.companies.length / run.total_companies} |

后端 `ImportResolutionResponse` 新增 `canonical_company_count` /
`canonical_contact_count`（distinct candidate，排除 rejected），Step 10 关闭页
的公司数同步改为 canonical 口径。

## 8. 是否改变评分算法

**没有。** `RoutingPolicyV11`、`fitness_equipment_v1`、`real-routing-v1.1`、
Preview/Apply evaluator、A/B/C/D 阈值、Country 语义、taxonomy 均未改动。
仅新增只读计数字段与 UX/error state 修复。

## 9. 测试结果

| 门禁 | 结果 |
| --- | --- |
| `uv run pytest`（后端全部） | **1260 passed**（新增 canonical-count 不变式 + KEEP_SEPARATE 计数回归） |
| `uv run ruff check .` / `uv run mypy app tests --strict` | 通过（431 文件） |
| 前端 `tsc --noEmit` / `lint` / `build` | 通过 |
| Playwright：bulk-import（Step 4→Step 5 恢复 + 新统计 + stage message + 无全局错误） | 通过 |
| Playwright：routing-batch-start / umail-export-suppression | 通过 |
| `uv run alembic heads` | 单 head `d5d2b1c2d3e4`，无新增 Migration |

## 10. Leo 下一步应该点击什么

Step 4 已全部完成（pending=0）。Leo 进入 Step 5：

1. 查看 Campaign 摘要（参数已由 preset 自动推导）。
2. 点击「生成开发优先级预览」，核对 A=2 · B=1 · C=31 · D=21（合计 55）。
3. 确认 D=21 中含 13 家 `NON_US_TARGET`（加拿大进口商）与显式非目标行业公司。
4. 启用真实数据开关，点击「生成客户优先级」并在确认框确认——**必须由 Leo 本人
   执行**，系统不会自动 Apply、不会发送邮件。
