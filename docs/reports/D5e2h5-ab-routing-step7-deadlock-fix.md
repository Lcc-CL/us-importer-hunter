# D5e2h5 — Fix A/B Routing Deadlock and Auto-Unlock Umail

## 结论

Step 6 改为业务化「客户开发分流」：A（优先深度开发）与 B（批量开发）在同一页面
并行展示与确认；B route 人工确认后 **Step 7 Umail Export 立即解锁（持久化，刷新
保留）**，不再依赖 A 分支状态。未重新跑 Routing、未改 RoutingPolicyV11/taxonomy、
未发送 Email、未替 Leo 确认 A/B。

---

## 1. 红色错误真实根因

生产页面「发生意外错误，请稍后重试。」来自前端 `getClientErrorDetails` 的
`unexpected_client_error` fallback（非 ApiError 分支），例如：

- `loadRoutedBatchState` 对非销售路由批次抛出的普通 Error
  （"batch is not sourced from sales routing"）；
- 未映射的已知业务状态码（如批次创建的前置校验码）走了泛化文案；
- 瞬时网络/超时错误。

修复：

- `loadRoutedBatchState` 的 source-kind 错误映射为业务中文
  「该批次不属于当前销售路由流程。」；
- 新增业务映射：`ROUTING_BATCH_COMPANIES_REQUIRED`（请选择至少 1 家优先客户）、
  `ROUTING_BATCH_LIMIT_EXCEEDED`（每批最多 5 家）、
  `ROUTING_BATCH_COMPANY_OUTSIDE_RUN` 等；
- Step 6→Step 7 的已知状态（B 未确认 / B=0）以业务文案展示，不再出现 generic。

## 2. 为什么 B=1 但 Step 7 之前未解锁

Step 7 的 gate 是 **human-confirmed / manually-overridden B route**（
`hasBRoute = routes.some(B && confirmed/overridden)`），不是 routing tier=B。
生产 B=1 但 route 仍为 `suggested`（Leo 尚未确认），且旧 UI 没有清晰的「确认批量
开发」入口（确认动作藏在路由明细表里，且路由表被逐步收敛），形成 deadlock：

```text
B route suggested → hasBRoute=false → Step 7 locked
                   → Step 6 无明确 B 确认入口 → 用户卡在 Step 6
```

## 3. 旧 Step 6 completion rule

`step6.complete = Boolean(routedBatch || hasBRoute)`：必须已创建深度分析 Batch
**或** 已有确认 B；A 未处理会卡住，且 B 确认入口不清晰。

## 4. 新 Step 6 rule

```text
step6.complete = routingComplete && bBranchResolved
  bBranchResolved = hasBRoute || bSkipped || bCount === 0
step7.unlocked  = routingComplete && bBranchResolved
```

- B confirmed ≥ 1 → Step 7 解锁（持久化，刷新保留）。
- B=0 → Step 7 解锁并显示「本批次没有批量开发客户。」（branch skipped）。
- A 分支不阻塞 B；A 未处理时 Step 6 内仍可继续操作。

## 5. A/B 是否已经完全解耦

是：A（深度分析：勾选 → 开始深度分析 CTA 内部确认 A route → 建批 → 启动）与
B（批量开发：勾选 → 确认批量开发 CTA 内部确认 B route → Step 7 解锁）互不
blocking；C/D 自动 terminal（暂缓/排除），无需 Leo 点击。

## 6. 是否新增 DB/Migration

**否。** 无新表、无 Migration；复用现有 Route review（confirm）API 持久化
approval；A/B skip 仅记录在 URL 参数（前端状态），未新增后端结构。

## 7. 是否执行真实业务动作

本轮代码/部署过程中**未执行**真实业务动作：未确认 A/B、未启动 Research、未执行
Umail export、未发送 Email；生产只读验证。

## 8. production deployment

合并后由 main 触发 Zeabur 自动部署（Frontend；后端零改动）；PostgreSQL/Redis 未
重建。生产只读 smoke：frontend 200、health ok、runtime capabilities 正常。

## 9. production 当前 A/B/C/D 数量

```text
A=2 · B=1 · C=31 · D=21 · blocked=0 · Total=55（只读 Preview 快照）
```

## 10. Leo 下一步需要点击什么

1. Step 6「客户开发分流」：A 区勾选优先客户（默认不勾选）→「开始深度分析
   （N/2）」（0 时显示提示并可「本批次跳过深度分析」）。
2. B 区勾选批量开发客户 →「确认批量开发（N 家）」→ Step 7 自动解锁。
3. 进入 Step 7 Umail Export 生成离线 CSV（不发送）。
4. C/D 无需操作。
