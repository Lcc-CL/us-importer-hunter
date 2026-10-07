# D5e2g.1 — Entity Review Decision Semantics Audit + UX Hardening

## 结论

**SAFE_FOR_LEO_ENTITY_REVIEW**

四个 Review 动作中没有任何一个会删除 Raw 数据或 Canonical 实体；REJECT 只拒绝
“该行与候选实体的关联”，且所有写入都是可审计、可恢复的。本轮完成按钮语义重命名、
低置信 MERGE 二次确认、tooltip/helper text 与安全回归测试，但**没有执行任何真实
Review decision、没有 Routing Apply、没有 Research/LLM/Umail/邮件发送**。系统停在
Leo 人工操作之前。

---

## 1. 审计范围与原则

本次为只读审计 + UI/API 表面修改 + 测试。追踪链路：

Frontend button → `reviewImportEntityDecision(decisionId, action)`
→ `POST /api/v1/import-entity-decisions/{decision_id}/review`
→ `ImportEntityReviewRequest` (schema `app/schemas/import_resolution.py`)
→ `ImportEntityReviewWorkflow.review` (`app/workflows/import_resolution/workflow.py:713`)
→ `ImportEntityDecision.review` (Domain, `app/domain/import_resolution/models.py:296`)
→ Repository/Mapper → PostgreSQL → refresh/recovery → Entity Resolution → Routing eligibility。

关键文件：

- Review workflow：`apps/backend/app/workflows/import_resolution/workflow.py`
- Domain decision：`apps/backend/app/domain/import_resolution/models.py`
- Decision API：`apps/backend/app/api/routes/import_resolution.py`
- 前端 Review Card / 确认框：`apps/frontend/src/features/bulk-import/bulk-import-panel.tsx`

---

## 2. 四个动作的真实语义（代码级结论）

| 动作 | 前端标签（修改后） | Domain 语义 | 修改的表 | 修改的字段 |
| --- | --- | --- | --- | --- |
| DEFER | 「暂缓判断」 | **没有后端动作**。`ImportReviewAction` 中不存在 defer；UI 按钮是 no-op，保持 `review_status=pending` | 无 | 无 |
| MERGE | 「确认同一实体」 | 确认该行与候选属于同一实体：把行的 source/channel 数据并入候选 Canonical 实体，并在 `import_entity_decisions` 记录 `manual_merge` | `import_entity_decisions`、`companies`/`company_sources`、`company_resolution_profiles`、`company_external_identities`、`contacts`/`contact_channels`、`contact_sources`、`company_contacts`、`import_resolutions` | decision→`manual_merge`、review_status→`reviewed`、reviewed_by/reviewed_at、candidate_entity_id 保留；公司/联系人的 sources、channels、profile、external identity、任职关系；resolution 计数 |
| KEEP_SEPARATE | 「确认不同实体」 | 确认不是同一实体：**创建新的 Canonical 实体**（公司或联系人）并绑定该行，决策记录 `keep_separate` | 同上（新增 companies/contacts + 相关行） | 同上；candidate_entity_id 指向新建实体 |
| REJECT | 「拒绝此候选关系」 | **只拒绝该行与候选实体的关联**（reject candidate match，任务书中六种含义的第 1 种）。`candidate_entity_id` 置 NULL，决策记录 `rejected`，不写任何 Canonical 数据 | `import_entity_decisions`、`import_resolutions` | decision→`rejected`、review_status→`reviewed`、reviewed_by/reviewed_at、candidate_entity_id→NULL；resolution 计数 |

### A–O 逐项回答

| 问题 | DEFER | MERGE | KEEP_SEPARATE | REJECT |
| --- | --- | --- | --- | --- |
| A. 修改哪张表？ | 无 | 见上表 | 见上表 | `import_entity_decisions` + `import_resolutions` |
| B. 修改哪些字段？ | 无 | 见上表 | 见上表 | decision/review_status/reviewed_by/reviewed_at/candidate_entity_id |
| C. 是否修改 Canonical Company？ | 否 | 是（新增 source、更新 profile） | 是（新建公司） | 否 |
| D. 是否修改 Contact？ | 否 | 是（新增 source/channel） | 是（新建联系人） | 否 |
| E. 是否修改 CompanyContact？ | 否 | 是（新增/更新任职关系） | 是（新增任职关系） | 否 |
| F. 是否删除 RawImportRow？ | 否 | 否 | 否 | 否 |
| G. 是否删除 source data？ | 否 | 否 | 否 | 否 |
| H. 是否删除 canonical entity？ | 否 | 否 | 否 | 否 |
| I. 是否只是拒绝 candidate relationship？ | — | 否 | 否 | **是** |
| J. 是否影响重新导入相同文件？ | 否 | 否（文件哈希相同会复用 session） | 否（新文件会按 external id 复用新建实体） | 否（重新导入会生成**新的** ImportSession 与新的决策） |
| K. 是否阻止未来再次产生同一候选？ | 否 | 否 | 在 stable external id 场景下，新导入会直接复用新建实体（不再提出冲突候选） | **否**（只影响本次 session；无 persistent exclusion） |
| L. 是否可以恢复/撤销？ | 是（保持 pending） | 部分可逆：写入是 add-only（source/channel 累加），Raw 数据保留，可通过重新导入重建；无 delete | 是（新建实体可由新导入/未来工具合并；Raw 数据保留） | 是（仅改决策状态；Raw/Canonical 数据完整） |
| M. 是否影响 Routing Preview？ | 是（保持 blocked） | 是（该实体进入可路由集合） | 是（该实体进入可路由集合） | 是（该行不再映射到任何实体，不参与路由） |
| N. 是否影响 A/B/C/D tier？ | 保持 blocked | 解除 blocked，按规则定级 | 解除 blocked，按规则定级 | 不产生新 tier 实体 |
| O. 是否可能导致真实数据不可逆丢失？ | 否 | 否（add-only 写入；无删除） | 否 | 否 |

### REJECT 到底表示哪一种？

**1. reject candidate match（拒绝候选匹配）**。代码证据：

```python
reviewed = decision.review(
    action=action,
    candidate_entity_id=(None if action is ImportReviewAction.REJECT else candidate_id),
    ...
)
```

`_resolved_entity_id()` 对 `REJECTED` 返回 `None`，后续 `_link_after_review` 不会为该行
创建 CompanyContact。没有任何 `delete()` 调用触及 Raw、Canonical 或 source 数据。

---

## 3. KEEP_SEPARATE vs REJECT 是否冗余？

| 维度 | KEEP_SEPARATE | REJECT |
| --- | --- | --- |
| Domain 意义 | 确认两条记录是**不同实体**，并为该行建立独立 Canonical 实体 | 拒绝该行与候选的**匹配关系**，不建立任何实体 |
| 数据库状态 | 新建 company/contact + profile + external identity + 任职关系 | 仅决策状态变化，candidate_entity_id=NULL |
| 后续重新导入行为 | 相同 stable external id 会直接复用新建实体（不重复提出候选） | 新 ImportSession 会**再次**提出同一候选 |
| Entity Resolution 是否再次提出同一 pair | 否（external id 命中即复用；无 external id 时仍可能再次匹配） | 是（每个新 session 重新计算） |
| Routing | 新建实体可参与后续路由 | 该行不映射到实体，不参与路由 |

**结论：两者语义真正不同，不是冗余。** REJECT 的按钮此前只写「拒绝」，容易让 Leo
误以为会删除实体/数据，因此本轮重命名为「拒绝此候选关系」并加 tooltip。

---

## 4. 数据库写入路径（每动作）

### DEFER

无请求，无写入。`review_status` 保持 `pending`，`candidate_entity_id` 不变。

### MERGE（公司）

1. `companies.add_source(...)` → `company_sources` 新增行；
2. `company_resolution_profiles` upsert（`seen_again` 合并 normalized 字段）；
3. `company_external_identities` 新增或 `seen_again`；
4. 决策行更新为 `manual_merge / reviewed`；
5. `_link_after_review` → `company_contacts` upsert；
6. `import_resolutions` 计数更新（`companies_reused += 1`）。

### MERGE（联系人）

1. `contacts` 更新 + `contact_sources` 新增；
2. `contact_channels` 按 (type, normalized_value) 去重后新增；
3. 决策行更新 + `company_contacts` 关联 + 计数更新。

### KEEP_SEPARATE

1. 新建 company/contact（`_create_separate_company/_create_separate_contact`）+
   `company_sources`/`contact_sources` + channels + profile + external identity；
2. 决策行 `candidate_entity_id` 指向新建实体，记录 `keep_separate / reviewed`；
3. `company_contacts` 关联 + `companies_created/contacts_created` 计数。

### REJECT

1. 决策行更新：`decision=rejected`、`review_status=reviewed`、`candidate_entity_id=NULL`、
   `reviewed_by/reviewed_at` 写入；
2. `import_resolutions` 计数更新；
3. 无任何 Canonical/source 写入。

---

## 5. 不可逆性分析

不存在删除型操作。唯一“消耗性”动作是 MERGE（把新行的 source/channel 并入现有实体），
但写入均为 **add-only**：company/contact 的 sources、channels、profile、external
identity 只累加不删除，Raw 行与决策审计记录始终保留，可通过重新导入重建独立实体。
因此四个动作都不会导致真实数据不可逆丢失。

---

## 6. UI 修改（前后对比）

| 按钮 | 修改前 | 修改后 |
| --- | --- | --- |
| DEFER | 「推迟（DEFER）」 | 「暂缓判断」+ tooltip「当前信息不足，保持待复核状态，不执行合并或分离。」 |
| MERGE | 「合并」 | 「确认同一实体」+ tooltip「确认两条记录属于同一家企业/同一联系人，并合并到同一 Canonical Entity。」 |
| KEEP_SEPARATE | 「保持分离」 | 「确认不同实体」+ tooltip「确认两条记录不是同一实体，并保留人工分离决策，避免相同候选反复出现。」 |
| REJECT | 「拒绝」 | 「拒绝此候选关系」+ tooltip「仅拒绝该行与候选实体的关联，不删除任何数据。」 |

低置信 MERGE（`confidence < 0.8` 或 reason 含 `company_name_similar` /
`same_company_name_only`）弹出二次确认框：

- 标题：「确认合并这两个实体？」
- 候选 A（新导入行）：行号 + source facts（公司名称/官网/邮箱等）
- 候选 B（现有实体）：名称、匹配置信度、匹配原因
- 提示：「合并后，两条记录将共享同一个 Canonical Entity。」

DEFER 不加确认框（no-op，无风险）。KEEP_SEPARATE 不加确认框（新建实体可恢复，风险低）。

变更文件：

- `apps/frontend/src/lib/i18n.tsx`（中英文案）
- `apps/frontend/src/features/bulk-import/bulk-import-panel.tsx`（按钮 + tooltip + 确认框）

---

## 7. 生产 pending 数量说明

部署后对生产实例 `usimporterhunter.zeabur.app` 做只读验证
（`GET /api/v1/import-sessions/{session}/entity-decisions?review_status=pending`）：

- **9 条 pending**：5 条 company `review_required` + 4 条 contact `review_required`
  （与任务书一致；D5e2g 报告当时为 10 条，此后已有 1 条 contact 决策被人工
  review 为 `keep_separate`，属既有状态，非本轮产生）。
- 前端不硬编码数量，从 `/entity-decisions?review_status=pending` 实时读取，
  因此 Review Card 显示的是真实数字。
- 本轮未对生产执行任何 Review/Routing/写入；本地开发库不包含生产数据
  （生产在 Zeabur 部署实例上）。

---

## 8. 技术债（本轮记录，不解决）

1. **Routing Preview 与 Routing Apply 使用不同评分器**：preview 用
   `RoutingPolicyV11`（real-routing-v1.1），apply/execution 用旧版
   `DeterministicProspectRoutingScorer`。两者在 origin 字段语义上可能产生分歧
   （preview 把 origin_country 当作进口商国家做 `NON_US_TARGET` 硬排除；真实网易
   「来源国」是供应商/发货国）。合成 fixture 中已复现 preview 全 D、apply 却 A/B 的
   差异。**这属于 D5e2f 系列遗留，不阻塞 Entity Review，但 Leo 应用 Routing 前必须
   统一。**
2. **Preview 的 reason code 截断**：`reason_codes[:8]` + `explicit_negative` 只识别
   `EXPLICIT_*`，导致 `NON_US_TARGET`/`FREIGHT_FORWARDER` 等硬排除原因在 UI 上不可见。
   已列入 Routing 可解释性债。
3. **无 persistent exclusion**：REJECT 只影响当前 session；若需要“永久排除某候选”，
   需要新增最小 persistent decision/exclusion 结构。现有 `import_entity_decisions`
   是 per-session 的，无法承载跨 session 的长期决策，因此需要新表/新字段。本轮按
   约束不创建，未来 migration path：`entity_exclusions(company/contact_id, source,
   excluded_at, reason, created_by)`，生命周期与 Canonical 实体绑定。
4. **DEFER 无后端动作**：按钮是 no-op，语义靠 UI 文案表达；若需要显式审计
   “某人看过但未决定”，未来可增加 `deferred` action 记录 reviewed_by/reviewed_at
   但保持 pending。
5. **KEEP_SEPARATE 在无 stable external id 时不能防止同一候选再次出现**（新 session
   重新计算）。需要 exclusion 结构才能彻底阻止。
6. **E2E 遗留**：`i18n.spec.ts` 两个用例针对旧 mvp-analysis 手动表单，当前落地页已
   改为批量导入验收工作台，在 HEAD 上即失败（与本次改动无关，已用 stash 验证）。

---

## 9. 测试结果

### 新增后端集成测试（6 个，真实 PostgreSQL）

`apps/backend/tests/database/integration/test_entity_review_semantics.py`：

1. `test_defer_leaves_canonical_entities_and_pending_state_untouched` — DEFER 不改变
   canonical 实体与 pending 状态；
2. `test_reject_rejects_only_candidate_match_and_never_deletes_data` — REJECT 只拒绝
   候选匹配：Raw/Company/Contact/CompanyContact 数量不变，无 link；
3. `test_keep_separate_persists_and_prevents_recurring_candidate_on_reimport` —
   KEEP_SEPARATE 持久化 + stable external id 下重新导入不重复提出候选；
4. `test_merge_is_persisted_and_idempotent` — MERGE 持久化且幂等（不重复生成决策）；
5. `test_department_mailbox_is_never_merged_or_linked_as_person` — 部门邮箱不会作为
   个人决策人；
6. `test_routing_preview_blocks_pending_entity_until_all_resolved` — pending > 0 时
   Routing Preview blocked；全部 resolved 后解除。

### 全量门禁

| 门禁 | 结果 |
| --- | --- |
| `uv run pytest`（后端全部，含 PostgreSQL 集成） | **1251 passed** |
| `uv run ruff check .` | **All checks passed** |
| `uv run mypy app tests --strict` | **Success: no issues found in 430 source files** |
| 前端 `tsc --noEmit` | 通过 |
| 前端 `npm run lint` | 0 errors（5 个既有 warning，非本次文件） |
| 前端 `npm run build` | 通过 |
| E2E `bulk-import.spec.ts`（Playwright, chromium） | **1 passed**（覆盖：refresh 后 review 恢复、pending 时 Routing blocked、低置信 MERGE 确认框、合并后解除 block、Routing apply 全流程） |
| E2E `i18n.spec.ts` | 2 failed —— **HEAD 上同样失败**（旧手动表单测试，与本次改动无关） |

---

## 10. Git 状态与提交

- 分支：`fix/d5e2g1-entity-review-semantics`（自 `main` @ `869e268` 创建）
- 变更：
  - `apps/frontend/src/lib/i18n.tsx`
  - `apps/frontend/src/features/bulk-import/bulk-import-panel.tsx`
  - `e2e/tests/bulk-import.spec.ts`
  - `apps/backend/tests/database/integration/test_entity_review_semantics.py`（新增）
  - 本报告
- 未触碰：生产数据、历史 Migration、`real-routing-v1` 语义、PR #4。

---

## 11. 是否允许 Leo 开始真实 Review

**是（SAFE_FOR_LEO_ENTITY_REVIEW）**。

前提与边界：

- 四个按钮语义已明确：暂缓（no-op）/ 确认同一实体（合并）/ 确认不同实体（新建独立实体）/
  拒绝此候选关系（仅拒绝匹配，不删数据）；
- 低置信 MERGE 有二次确认，展示候选 A/B 事实；
- 没有任何动作删除 Raw/Canonical 数据；
- Routing Apply 仍被 pending 决策阻塞（`entity_pending_count > 0` 时禁用）；
- 本轮未自动执行任何真实 decision、未调用 Research/LLM/Umail、未发送邮件。

Leo 可开始人工复核；全部 pending 解除后，Routing Preview/Apply 再进入下一阶段
（届时必须先解决第 8 节第 1 条的 preview/execution 评分器分歧）。
