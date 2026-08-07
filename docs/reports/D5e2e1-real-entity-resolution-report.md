# D5e2e1 First Real Import Post-Write Diagnosis + Entity Resolution 报告

日期：2026-08-07

## 最终状态

**READY_FOR_REAL_ROUTING** —— 真实 Entity Resolution 已完成（52 公司 / 118
联系人 / 113 CompanyContact 已持久化）；10 个 name-only 决策**等待 Leo Review**；
Routing 未执行。

## 1. Red error 根因

- 失败请求：`GET /api/v1/import-sessions/{session}/resolution` → **404**
  `resource_not_found`（归并尚未创建时的 Step-4 恢复读请求）。
- 属 B 类：**Import 已成功**（session completed、127 行持久化），失败是导入后的
  follow-up 读请求；不是 Import 事务失败，未把 Import 标记为 failed。
- 页面 “Something unexpected happened…” 来自前端对非 ApiError 形状响应的
  generic fallback（旧前端状态/瞬时轮询失败）；后端错误本身均为结构化
  ApiErrorPayload（含 request_id）。
- 修复（PR #19，已合并 994459a 并部署）：工作流进度由 persisted 状态推导；
  已知错误码映射中文业务信息；轮询失败在下次成功时清除。复测无 generic 错误、
  无失败请求。

## 2. ImportSession 持久化事实

- session `2850767c-64b9-4f3b-b2d9-114faced146d`：status=completed，
  file_type=xlsx，filename=2026-08-07_fitness_equipment.xlsx，
  SHA-256=aabf7664…77fd，encoding=xlsx-xml；
- RawImportRow=127（row_number 唯一，全部保留 raw_payload/sheet）：
  accepted 125、duplicate 2、invalid 0 —— 与 UI 对齐（127/125/2/0）。

## 3. Duplicate 语义

- duplicate rows：52、59（error_codes=["duplicate_row"]）——与前面行**整行值完全
  相同**的重复（hash 级重复），**不是** contact continuation 行；
- 72 个 continuation 行全部为 accepted（合并单元格继承，未误标 duplicate）。

## 4. 幂等

唯一约束 `uq_import_sessions_source_hash` 存在；同 hash 仅 1 个 session
（2850767c…）；重复提交同一 XLSX 由 service 复用既有 session，不产生第二个
有效 ImportSession（本轮未真重复上传，仅只读验证约束与路径）。

## 5. Workflow progress 修复

- 旧 bug：步骤完成度由前端临时状态（preflight/mappingConfirmed）推导，刷新后
  “当前可执行”回退到 Step 1；
- 修复：由 persisted session/resolution 推导（有 session ⇒ Step1-3 完成；
  resolution completed ⇒ Step4 完成）；“当前可执行”= 第一个未完成的已解锁步骤；
  增加“下一步”提示；刷新不回退（生产实测两次 reload 均为
  “当前步骤 Step 4 · 当前可执行 Step 5 · Routing”）。

## 6. 真实 Entity Resolution 结果

- 任务提交：POST /resolve → 202（job f8dc661c）；worker 1 次执行完成，
  processed 125/125，attempts 1；
- **Company**：52 canonical companies 已创建（55 anchors；2 组
  domain+name HIGH 归并由确定性 matcher 自动合并；与 Preflight 估计 53 的差异
  来自 matcher 实际规范化，以真实结果为准）；
- **Contact**：118 created + 2 reused；CompanyContact=113；
- **Department contacts**：12 个共享邮箱已落
  `company_contacts.is_department_contact=true`，且 PR #17 保证不会自动成为
  Decision Maker；
- **Pending review**：10 个 name-only 决策（5 company `company_name_similar`
  + 5 contact `same_company_name_only`，confidence 0.55）——按规则不自动 merge，
  等待 Leo Review（未代决）；
- 决策表：250 条（10 pending，0 reviewed）。

## 7. 持久化计数（生产）

companies 52 · contacts 118 · company_contacts 113 ·
company_external_identities 0 · opportunities 0 · prospect_routes 0 ·
email_drafts 0 · import_processing_jobs 1 · raw_import_rows 127 ·
import_entity_decisions 250（10 pending）。

## 8. Refresh / Recovery

生产页面两次 reload：Step 4 + resolution 面板 + 待复核决策保持，无 generic
错误、无失败请求；Worker/Backend 健康（ready 200，WORKER_HEARTBEAT_OK）。

## 9. 合规

未调用外部 Provider / LLM；未发送邮件；未执行 Routing / ProspectBatch /
Research / Draft / Umail Export。

## 10. Remaining blocker

Step 4 的 10 个 name-only 决策（5 公司 + 5 联系人）需 Leo 在 UI Review 后，
才能进入 Step 5 Routing。

## 11. Technical debt

同前：chunk/batch parser 非 streaming；完整 Employment History；fuzzy company
ML matching；Umail API；自动邮件发送；分布式 ingestion queue。
