# D5e2h2 — A-Tier Automatic Deep Analysis Launch Audit

## 结论

深度处理链路（Batch → Job → Worker → Research → Evidence → Scoring → Contact →
Decision Maker → Draft）**已完整实现且由 Worker 自动推进**；UX 已简化为
「开始深度分析（N 家）」一键 Create + enqueue + Worker start。但生产配置审计发现：

```text
research_provider = deepseek（真实）
email/draft provider = fake（非真实）
```

生产安全门禁 `ensure_available` 明确禁止 fake provider 启动深度处理
（"fake prospect pipeline providers are disabled in production"），因此
**当前两家 A 类公司 NOT SAFE_TO_START**——点击「开始深度分析」会被服务端拒绝。
UI 已显示「当前未配置真实 Research Provider」阻塞提示。状态：

**BLOCKED（缺少真实 Draft/Email Provider）** —— 不是
`READY_FOR_FIRST_REAL_DEEP_ANALYSIS`。

本轮未启动任何真实 Batch；未自动接受 Evidence、未批准 Draft、未发送邮件、
未修改 Routing 算法、未新增 Discovery Provider。

---

## 1. 当前系统是否已经可以自动深度分析

**代码能力：是。生产可用性：否（Provider 门禁）。**

执行链（`app/workflows/prospect_batch/`）：

```text
ProspectBatch（创建/复用）
→ ProspectJob（PostgreSQL 租约队列，ProspectJobCoordinator）
→ Worker（app/worker.py 的 ProspectJobRunner.run_once）
→ ProspectBatchWorkflow.execute（逐个公司自动推进）
   VALIDATING → RESEARCHING
   → AWAITING_EVIDENCE_REVIEW（有 claim 待审时暂停）
   → SCORING → DISCOVERING_CONTACT → Decision Maker → GENERATING_DRAFT
   → NEEDS_REVIEW（Draft 等待人工批准）或 COMPLETED / FAILED
```

Worker 一次领取一个 job，自动跑完批内所有 active 公司；某家公司异常不会中止
整批。失败可 `retry`（可重试错误码），证据审核后可 `resume`。

## 2. Research Provider 是否真实可用

| 项 | 生产配置（只读 runtime，无密钥） |
| --- | --- |
| provider type | `deepseek`（`research_provider=deepseek`，`research_model=deepseek-v4-pro`） |
| production enabled | 是（`environment=production`） |
| real / fake | **real**（会向 DeepSeek API 发起真实外部请求并产生成本） |
| 审计 | ResearchRun 记录 `extractor`（provider/model）、`started_at`、`completed_at`、`status`；duration 可由时间戳推导；token/cost 若可获得记录在日志 |

## 3. Draft Provider 是否真实可用

| 项 | 生产配置（只读 runtime，无密钥） |
| --- | --- |
| provider type | `fake`（runtime `provider=fake`，`model=fake-static-v1`） |
| production enabled | 否——`ProspectPipelineProviderConfiguration.ensure_available` 在生产环境拒绝 fake |
| real / fake | **fake**（不会产生真实 LLM 请求，但整条 pipeline 被门禁拦下） |
| 结论 | **Draft Provider 未配置真实后端（如 openai），这是当前 BLOCKED 的唯一硬阻塞** |

## 4. Contact 数据来源

仅使用**公司官网公开数据**：`ContactDiscoveryRunner` 从已 Research 的页面
（website/contact/about 等公开页）提取联系人（姓名/职位/邮箱/电话 + source_url）。
**没有外部联系人 Provider**（无付费联系人 API）；部门邮箱不会被自动选为
Decision Maker；ambiguous 时进入 `DECISION_MAKER_NOT_SELECTED` 等待人工。

## 5. 点击「开始深度分析」后实际会发生什么

1. 前端一个按钮：若 Batch 未创建 → `createRoutedProspectBatch`（创建 Batch）；
   随后 `startRoutedProspectBatch`（`confirmation=true`、`provider_mode=configured`）。
2. 服务端 `ensure_available` 校验：**生产 + fake provider → 503 拒绝**
   （当前生产状态，因此实际不会启动）。
3. 若 Provider 真实：创建 ProspectJob → Worker 领取 → 自动跑
   research → scoring → contact → DM → draft；仅在证据审核/DM 歧义/Provider
   失败/Draft 批准处暂停。
4. 全程不自动接受 Evidence、不自动批准 Draft、不发送邮件。

## 6. 哪些阶段完全自动

- 官网 Research（真实 Provider 时）
- 机会评分（Opportunity/Scoring）
- 公开联系人识别
- Decision Maker 选择（无歧义时）
- Draft 生成（真实 Provider 时）

## 7. 哪些阶段需要 Leo

- **Evidence Review**（research claim 待审，`awaiting_evidence_review` → 审后
  resume）
- **Entity/Decision-Maker 歧义**（`CONTACT_UNUSABLE` / `DECISION_MAKER_NOT_SELECTED`
  → 人工处理）
- **Insufficient trusted evidence**（`INSUFFICIENT_TRUSTED_EVIDENCE`）
- **Provider failure**（需要人工决定 retry/review）
- **Draft 批准**（`needs_review`：Draft 已生成，等 Leo 审阅）

## 8. 是否存在真实 LLM/API 成本

- Research：**会**（DeepSeek，真实外部请求，生产已启用）。
- Draft/Email：当前为 fake，不产生成本；若配置 openai 后会产生。
- 结论：在 Draft Provider 未真实化之前，整条链路被门禁拦截，**不会产生任何
  成本**。

## 9. 当前两家公司是否 SAFE_TO_START

**否（NOT SAFE_TO_START）**。TUFF TORQ / PURSUE MOVEMENT 即便 A 类且路由已确认，
点击开始也会被生产 fake-provider 门禁拒绝；必须先配置真实 Draft/Email Provider
（或显式接受该限制）。

## 10. Leo 下一步只需要点击哪个按钮

现在**不要点击「开始深度分析」**——先解决配置：

1. 配置真实 Draft Provider（`EMAIL_GENERATOR_PROVIDER=openai` + key/model），
   或确认接受 fake 限制（当前设计不允许生产 fake）。
2. 配置后 UI 自动消失「当前未配置真实 Research Provider」提示。
3. 届时 Leo 在 Step 6 只点一次：**「开始深度分析（2 家）」**（确认框确认），
   Worker 自动推进，Leo 只需在 Evidence Review 与 Draft 批准处人工操作。

---

## 附：本轮 UX 变更与验证

- Step 6 两步骤（创建深度处理批次 → 启动深度处理）合并为一个
  「开始深度分析（N 家）」；Batch 已建未启动时按钮仍为「开始深度分析」。
- Generation / Batch ID 移入「技术详情 / 高级信息」（默认折叠）。
- A 类卡片显示业务阶段（等待分析/研究中/等待证据审核/评分中/联系人识别中/
  生成 Draft/完成/等待人工审核/失败）+ 进度（完成/待审核/失败）+ 最近更新 +
  错误原因 + Retry/Resume。
- 未配置真实 Provider 时显示阻塞提示并禁用按钮。
- 门禁：前端 tsc/lint/build 通过；Playwright bulk-import（一键启动 + 深度处理
  已启动）、routing-batch-start（start/resume/refresh）、umail-export-suppression
  通过；后端 ruff/mypy/定向 routing+parity 测试通过（后端本轮零改动）。
