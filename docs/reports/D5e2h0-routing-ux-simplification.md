# D5e2h0 — Routing UX Simplification for Sales Operator

## 结论

Step 5 主界面已收敛为「客户开发优先级」：Campaign 摘要 + 一键生成 + 高级筛选
规则折叠。**Routing 算法、taxonomy、rules_version、Preview/Apply parity、真实
数据安全门禁全部未变**（后端仅新增 1 个“无 HS/POL/POD 也能 Preview”的回归测试）。
未执行任何真实 Routing Apply / Research / LLM / Umail / 邮件。

---

## 1. 修改前后的操作步骤数

### 修改前（业务用户视角）

1. 进入 Step 5
2. 手动填写 6 个字段：目标产品关键词、HS Code、来源国偏好、POL、POD、Campaign 名称
3. 点击「生成 Routing 预览」
4. 检查 A/B/C/D
5. 点击「创建销售路由任务」
6. 在确认框里核对
7. 确认应用

### 修改后

1. 进入 Step 5（参数已由 preset 自动填好，无需输入）
2. 查看 Campaign 摘要（目标市场 / 目标行业 / 供应链偏好 / 规则版本）
3. 点击「生成开发优先级预览」
4. 检查 A/B/C/D/Blocked
5. 点击「生成客户优先级」
6. 在确认框里核对
7. 确认应用

手动输入步骤从 **6 个字段 + 4 次交互** 降为 **0 个字段 + 4 次交互**。

---

## 2. 哪些字段现在自动推导

最小 Campaign preset `fitness-equipment-us-v1`（JSON 配置对象，无新表）：

| 配置项 | 值 | 用途 |
| --- | --- | --- |
| `market` | 美国 | 摘要「目标市场」 |
| `target_taxonomy` | `fitness_equipment_v1` | 摘要「目标行业：健身器材」 |
| `origin_preference` | China | 摘要「供应链偏好」+ 高级筛选默认值 |
| `routing_policy` | `real-routing-v1.1` | 摘要与高级筛选「规则版本」 |
| `target_product_keywords` | `fitness, gym equipment` | Preview 参数（自动） |
| `target_hs_codes` | 空 | 高级筛选默认「未设置」 |
| `preferred_pol / preferred_pod` | 空 | 高级筛选默认「未设置」 |
| `campaign_name` | `fitness-equipment-us-v1` | Apply 的 campaign 标识（自动） |

规则版本在 Preview 生成后以 API 返回值（`real-routing-v1.1`）为准，不再硬编码展示。

---

## 3. 哪些移入高级设置

「高级筛选规则」（默认折叠，`<details>`）：

- 目标产品关键词
- 目标 HS Code
- 来源国偏好
- POL 偏好
- POD 偏好
- 规则版本（只读）

所有字段 optional；空值显示「未设置」（不再使用 `/`）。HS Code / POL / POD 缺失
不阻止 Preview（后端新增回归测试 `test_preview_without_hs_or_pol_pod_still_succeeds`）。

---

## 4. 是否改变 Routing 算法

**没有。**

- evaluator：`RoutingPolicyV11`（不变）
- taxonomy：`fitness_equipment_v1`（不变）
- rules_version：`real-routing-v1.1`（不变）
- Preview / Apply parity：单 evaluator 结构不变，Parity 集成测试全部通过
- pending Entity Review gate：不变（`entity_pending_count > 0` 时 Apply 禁用）
- CTA 按钮仅重命名，不改变行为；确认框、Apply 安全门禁保留

---

## 5. 是否新增技术债

少量、明确的配置对象技术债：

1. **单一 Campaign preset 为前端 JSON 常量**：MVP 只有单一真实业务场景，暂不建
   Campaign Management domain（P2）。后续多场景时迁移为后端配置对象/API 即可。
2. **preset 与真实 ImportSession 字段未做运行时校验**（例如目标产品与文件产品
   是否一致）：当前由 Preview 结果与人工确认兜底，记录为后续 enhancement。
3. 无新表、无新队列、无 ML/LLM；未新增 Migration（`alembic heads` 仍为单 head）。

---

## 6. 测试与 production smoke

| 门禁 | 结果 |
| --- | --- |
| `uv run pytest`（后端全部） | **1259 passed** |
| `uv run ruff check .` / `uv run mypy app tests --strict` | 通过 |
| 前端 `tsc --noEmit` / `lint` / `build` | 通过 |
| Playwright：bulk-import（preset 自动填充 + pending gate + 全流程） | 通过 |
| Playwright：routing-batch-start / umail-export-suppression | 通过 |

部署后 production 只读 smoke（`https://usimporterhunter.zeabur.app`）：

- frontend 200、`/api/v1/health` ok
- 生产 ImportSession 只读：**pending entity = 0** —— 9 条 Entity Review 已在
  D5e2g.2 与 D5e2h0 之间由 Leo 完成（2 条 company `manual_merge` + 3 条 company
  `keep_separate` + 5 条 contact `keep_separate`），非本系统/本轮执行。
- 生产 Preview（只读，D5e2h0 preset 参数，无 HS/POL/POD）：
  `real-routing-v1.1`、`preview_valid=True`、**A=2 · B=1 · C=31 · D=21 · blocked=0**
  （52 家全部出 tier；此前 blocked 的 FULFLEX→C 60.24、PRO PAK→C 68.95；
  TUFF TORQ A 93.95、PURSUE MOVEMENT A 76.45、LION HEART GYM B 68.45 不变）。
- ProspectRoute=0、Opportunity=0、Research=0、Umail=0、邮件=0

---

## 7. 下一步 Leo 需要点击什么

1. Step 4 已全部完成（pending=0，Leo 已人工复核）。
2. 进入 Step 5，查看 Campaign 摘要（无需填写任何字段，参数由 preset 自动推导）。
3. 点击「生成开发优先级预览」，核对 A/B/C/D（当前生产 Preview 为
   A=2 · B=1 · C=31 · D=21）。
4. 确认无误后启用真实数据开关，点击「生成客户优先级」并在确认框确认——**必须由
   Leo 本人执行**，系统不会自动 Apply、不会发送邮件。
