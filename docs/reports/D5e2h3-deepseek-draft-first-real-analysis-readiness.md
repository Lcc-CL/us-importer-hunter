# D5e2h3 — DeepSeek Draft Provider + First Real Deep Analysis Readiness

## 结论

**READY_FOR_FIRST_REAL_A_TIER_DEEP_ANALYSIS**（代码与配置就绪；本轮未替 Leo
点击「开始深度分析（2 家）」，未启动真实 Batch、未接受 Evidence、未批准 Draft、
未发送邮件、未改 Routing 算法）。

Draft Provider 已从 fake 切换为 **DeepSeek**（复用现有 OpenAI-compatible 传输，
无第二套 HTTP SDK），生产 Backend/Worker 均配置 `EMAIL_GENERATOR_PROVIDER=deepseek`；
Email sending 恒为 disabled。

---

## 1. Research Provider 最终状态

- type：`deepseek`（`RESEARCH_EXTRACTOR_PROVIDER=deepseek`）
- model：`deepseek-v4-pro`（`RESEARCH_MODEL` / `DEEPSEEK_MODEL`）
- production ready：**是**（生产配置存在 key/model/base_url，值未输出）
- 会产生真实外部请求（DeepSeek API）与真实成本
- 审计：ResearchRun 记录 provider/model/started_at/completed_at/status；duration
  由时间戳推导；usage tokens 若 DeepSeek 返回则记录，不伪造

## 2. Draft Provider 最终状态

- type：`deepseek`（`EMAIL_GENERATOR_PROVIDER=deepseek`，Backend + Worker 均已设置）
- model：`deepseek-v4-pro`
- production ready：**是**（与 Research 共用 DeepSeek key/model/base_url；
  `OpenAIEmailDraftGenerator` 增加 `base_url/provider` 参数复用同一
  OpenAI-compatible 客户端，`_build_client` 按 provider 读取
  `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`）
- 不产生 Email 发送（生成 Draft 与发送邮件语义分离）
- 输入继续使用现有结构化 Prompt（`app/prompts/sales/first_outreach`）与
  `OutreachDraft` domain；provider 异常/schema invalid/timeout → 现有
  `EmailGenerationError` → `DRAFT_GENERATION_FAILED` → retry/failed/review，
  不静默生成 fake Draft

## 3. Email sending 状态

**始终 disabled**：`runtime.email_send_enabled=false`，MVP 不发送邮件。

## 4. Provider 配置是否真实

是（生产只读 runtime 验证）：`research_provider=deepseek`、
`draft_provider=deepseek`、`draft_available=true`（部署后验证）、
`email_send_enabled=false`。API key 未在报告/输出中打印。

## 5. UI 修复结果

- 运行状态模型拆分：Research（DeepSeek · Ready）、Draft（provider · Ready/Blocked）、
  Email（Disabled）三个独立 capability 展示（`provider-badge` + runtime API 新增
  `draft_provider/draft_model/draft_available/email_send_enabled`）。
- 不再显示错误的「当前未配置真实 Research Provider」；深度分析阻塞提示改为
  「Draft Provider 尚未配置，因此深度分析暂不能启动。」（Draft 未就绪时禁用）。
- 成功 Preview/refresh 后清除 stale generic error（`loadRoutingPreview` 成功
  `setError(null)`；轮询错误 scoped 到 `pollError`）；`provider_unavailable`
  错误码映射为业务中文。

## 6. A 默认选择是否为 2

是（生产 A=2：TUFF TORQ / PURSUE MOVEMENT）。默认选择规则：A ≤ 5 全选，
A > 5 按 pre_score 取前 5；用户可取消选择（数量实时更新，按钮文字随
`selectedACompanies.length` 变化）。StrictMode 安全（副作用移出 state updater）。

## 7. 一键启动是否 ready

是：单按钮「开始深度分析（N 家）」→ Create/Reuse ProspectBatch → Create Job →
enqueue → Worker start；Generation/Batch/Job ID 在折叠的「技术详情/高级信息」。
Draft Provider 就绪后按钮启用（生产 real-data 模式下不再被 fake 门禁拦截）。

## 8. 测试结果

| 门禁 | 结果 |
| --- | --- |
| `uv run pytest`（后端全部） | **1264 passed**（新增 DeepSeek draft、runtime capability、production gate 正向用例） |
| `uv run ruff check .` / `uv run mypy app tests --strict` | 通过（431 文件） |
| 前端 `tsc --noEmit` / `lint` / `build` | 通过 |
| Playwright：bulk-import（默认选择 + 取消选择 + 一键启动）、routing-batch-start、runtime-health-capability、umail-export-suppression | **13 passed** |
| fake provider 生产 fail-closed | 保持（503） |
| email sending disabled | runtime 断言 |

## 9. 部署 commit

合并后由 main 触发 Zeabur 自动部署（Backend/Worker/Frontend）；PostgreSQL/Redis
未重建。生产 env：`EMAIL_GENERATOR_PROVIDER=deepseek`（Backend + Worker）已设置。

## 10. 是否产生真实 API 请求

本轮：**未产生**（未启动真实 Batch）。配置就绪后，第一次由 Leo 点击启动才会触发
DeepSeek Research 请求（以及后续 Draft 请求）。

## 11. 是否产生真实业务写入

本轮：**未产生**（ProspectRoute/Batch/Job/Research/Draft 均为 0 新增；生产只读验证）。

## 12. 当前技术债

- **P1：Research/Draft availability 全局门禁耦合**。理想状态：Research 可用即可
  先跑 Research/Scoring/Contact，Draft 不可用仅在 Draft 阶段暂停。本轮因
  Research/Draft 均为 DeepSeek、不阻塞 MVP 闭环，暂不做 capability pipeline
  重构（重构收益 < 风险）。
- DeepSeek Draft 的 usage/token 仅在可获得时记录（不伪造）；duration 由
  started_at/completed_at 推导。

## 13. Leo 下一步动作

1. 在 Step 6 确认 A=2 已默认选中（TUFF TORQ / PURSUE MOVEMENT），按钮显示
   「开始深度分析（2 家）」。
2. 点击「开始深度分析（2 家）」并在确认框确认——**必须由 Leo 本人执行**。
3. Worker 自动推进 Research → Evidence（需审时暂停）→ Scoring → Contact →
   Decision Maker → Draft；Leo 仅在 Evidence Review 与 Draft 批准处人工操作。
4. 邮件永不自动发送。
