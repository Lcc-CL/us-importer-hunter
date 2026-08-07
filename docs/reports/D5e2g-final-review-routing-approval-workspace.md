# D5e2g Final Entity Review + Routing Approval Workspace 报告

日期：2026-08-07

## 最终状态

**READY_FOR_LEO_UI_REVIEW_AND_FIRST_ROUTING_APPLY** —— Review 工作台、只读
Routing Preview API、Apply gate 与确认流程已上线；未替 Leo 做任何 decision，
未执行 Apply。

## 1. Implementation status

- **Step 4 Entity Review 工作台**：待审核计数（公司/联系人冲突、进度）、Review
  Card（Entity Type、Source Row、Candidate、Reason、Confidence、source facts、
  部门邮箱徽标）、操作 MERGE/KEEP_SEPARATE/DEFER（默认 DEFER）、低置信/name-only
  MERGE 二次确认、进度随 review 更新；决策持久化沿用现有 backend 链路（刷新
  恢复）。
- **只读 Routing Preview API**：`POST /import-sessions/{id}/routing-preview`
  （real-routing-v1.1 + fitness_equipment_v1；不创建 ProspectRoute），返回
  totals、per-company 卡片（positive/unknown/explicit 证据、product/HS/import
  信号、contact quality、data completeness、rules version）、preview_valid、
  entity_pending_count。
- **Step 5 Routing Review UI**：A/B/C/D/Blocked 数量卡 + 图例 +
  “Tier 是开发优先级，不是成交概率。”；公司卡片 + All/A/B/C/D/Blocked 过滤 +
  score 降序；Apply gate（pending=0 且 preview valid 且 rules version 且
  real_data_gate=enabled），否则禁用并显示 blocker；Apply 确认 modal
  （A/B/C/D 汇总 + “本操作不会自动发送任何邮件。”）；复用既有
  `POST /routing-runs`（幂等：reused/recalculated）。
- 错误码中文映射（ENTITY_REVIEW_PENDING / ROUTING_PREVIEW_INVALID /
  invalid_state / internal_error 等）。

## 2. PR / commit / deployment

- PR #24（review 工作台 + preview API + approval UI）Squash Merge → `37f06ce`；
- 热修 `15a6ac8`（entity_pending_count 含全部 10 条决策）直接提交 main；
- Backend/Worker/Frontend 均 RUNNING（自动部署 + Backend 手动 redeploy 修复一次
  镜像拉取 ImagePullBackOff）。

## 3. Production state（只读，未改数据）

- Pending entity：**10**；生产 Preview：**A=2 · B=1 · C=39 · D=8 · blocked=2**；
  preview_valid=True；rules=real-routing-v1.1，taxonomy=fitness_equipment_v1；
- A：TUFF TORQ、PURSUE MOVEMENT；B：LION HEART GYM；
- ProspectRoute=0 · Opportunity=0 · Research=0 · Provider calls=0 · LLM=0 ·
  Umail exports=0 · Emails sent=0；
- Apply gate：disabled（entity pending=10 > 0；real_data_gate=blocked）。

## 4. Technical decision

沿用 Next.js 现有状态 + 现有 Entity Resolution/Routing APIs；未引入
Redux/Zustand/WebSocket/新 workflow engine/新 review service（单用户 MVP，
避免双重状态源）。

## 5. Technical debt

多人 reviewer、review assignment、RBAC、实时协作 review —— 延期（不影响
单用户 MVP 闭环）；taxonomy 人工维护；ML/learned ranking 待真实结果标签。

## 6. Remaining blockers

1. Leo 在 Step 4 完成 10 条 review（默认 DEFER）；
2. Leo 启用真实数据开关（REAL_DATA_ACKNOWLEDGED=true，Backend）并确认 Preview；
3. Leo 点击“确认应用 Routing”（A 类 ≤5 家/批；B 类进 Umail 候选池不发送）。

## 7. 合规

自动化未触碰真实 ImportSession；生产仅只读验证；未替 Leo 点击 Review/Apply；
未调用外部 Provider/LLM/Umail；未发送邮件。
