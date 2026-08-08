# D5e2h4 — Single Page Human Review Console

## 结论

Evidence Review 已收敛到当前 Workflow 主页面（HumanReviewCenter「待我处理」），
不再依赖「打开公司工作台 → 找 Evidence → 返回 → 继续处理」的跳转链。人工完成
全部 Evidence decision 后，系统在 pending=0 时自动调用现有 Resume API 继续
深度分析（幂等）。本轮为纯前端 + 报告变更（后端零改动），未替 Leo 审核真实
Evidence、未 Resume 真实 Batch、未发送邮件。

---

## 1. 原 UX 问题

- 审核路径：当前页面 → 点击「审核证据」（deep-link 到公司工作台
  `#research-panel`）→ 寻找 Evidence → 审核 → 返回 → 再点「审核完成，继续处理」。
- deep-link 依赖 DOM anchor 与 URL 参数组合，可能跳转后找不到对应内容。
- 「继续处理」由用户点击 Resume，与“系统自动处理，人只处理必须判断的事项”
  的产品原则冲突。

## 2. 新 UX 操作路径

```text
Workflow 页面顶部「待我处理」
→ 证据审核：2（点击滚动到 Batch 内 Evidence Review 区）
→ 公司卡片「审核 N 条证据」→ 当前页面展开 inline EvidenceReviewCard
→ 每条 claim「确认有效 / 不采用」→「提交审核结果」
→ pending=0 → 自动 Resume →「证据审核已完成，系统正在继续分析。」
```

## 3. Evidence Review 是否可单页完成

**是。** `EvidenceReviewCard` 直接在 Batch 卡片内展开：显示 claim/assertion、
evidence snippet、source URL（「查看来源」新窗口打开；缺失时显示
「该 Evidence 没有可访问来源 URL。」）、confidence、审核进度（已处理 X / N）。
决策按钮复用后端真实语义（accept/reject → 「确认有效 / 不采用」；后端无
defer，故不新增），提交流程复用 `POST /research/runs/{id}/confirm`。

## 4. 是否仍需要 Company Workspace

不再作为审核路径；保留「查看公司详情 →」作为 secondary link。

## 5. Auto Resume 是否实现

**是。** 最后一个 Evidence decision 提交成功 → refresh 后端 run →
`pending claims = 0` → 自动调用现有 `POST /prospect-batches/{id}/companies/{cid}/resume`
（幂等）。失败显示「审核已保存，但系统继续处理失败。可以安全重试。」+
「重试继续处理」按钮。不自动接受/拒绝 Evidence——每个决策仍由 Leo 点击。

## 6. 是否新增数据库模型

**否。** 无新表、无 Migration（alembic 单 head 不变）；复用现有
research/batch/resume API 聚合前端状态。

## 7. 测试结果

| 门禁 | 结果 |
| --- | --- |
| 前端 `tsc --noEmit` / `lint` / `build` | 通过 |
| Playwright：routing-batch-start（单页审核 + 提交 + 自动 Resume + refresh 恢复 + 「待我处理」计数 + 无 start CTA）、bulk-import、runtime-health-capability、umail-export-suppression | **13 passed** |
| 后端 ruff / mypy / 定向 routing + parity 测试 | 通过（本轮后端零改动） |
| 无 stale generic error（e2e 断言 `global-error` 不可见） | 通过 |
| 不自动接受 Evidence / 不自动批准 Draft / 不发送 Email | e2e 断言「没有发送邮件」+ 决策按钮人工触发 |

## 8. production 状态

合并部署后三服务 RUNNING；PostgreSQL/Redis 未重建。生产只读 smoke：
frontend 200、health ok、runtime capabilities 正常（research/draft deepseek、
email disabled）。

## 9. 当前两家公司状态

TUFF TORQ CORPORATION / PURSUE MOVEMENT INC. 均为 `EVIDENCE_REVIEW_REQUIRED`
（awaiting_evidence_review），Research claims 已持久化，Draft=0。生产只读确认
（任务书状态 + 本轮未改动）。

## 10. 是否发生真实 Evidence decision

**否。** 本轮未替 Leo 审核任何 claim（e2e 使用 mock 数据；生产未写入 decision）。

## 11. 是否 Resume 真实 Batch

**否。** 未对生产 Batch 调用 resume；自动 Resume 仅在 Leo 完成真实 decision 后由
前端触发。

## 12. 是否发送 Email

**否。** email sending 恒为 disabled。

## 13. 技术债

- **P2：Human Review 仍由前端聚合多个 domain API**（evidence/batch/entity/draft）。
  若未来 Human Review 类型明显增加，再建立统一 backend AttentionItem/HumanAction
  模型；当前 MVP 不重构。
- Evidence Review 的「展开/折叠」状态为前端 local state（刷新恢复由后端
  pending 计数驱动，不受影响）。

## 14. Leo 下一步只需要做什么

在 Workflow 页面「待我处理 → 证据审核：2」：

1. 对 TUFF TORQ 与 PURSUE MOVEMENT 分别点「审核 N 条证据」。
2. 逐条选择「确认有效 / 不采用」→「提交审核结果」。
3. 每家 pending=0 后系统自动继续分析；Leo 仅在 Draft 生成后到「开发信审核」
   处人工批准。
4. 全程无需打开公司工作台、无需手动点 Resume、无需点「开始深度分析」。
