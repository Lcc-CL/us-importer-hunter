# Current Task: Stage 4A.4.3 Import Evidence Signal Promotion

**状态**: PASS；Stage 4A.4.3 已完成，后续 Stage 尚未开始

**分支**: `feat/v0.3-import-evidence-agent`

**Stage 4A.4.2 closure HEAD**: `d6a1eb8`

**日期**: 2026-07-21

**本阶段 commits**:

- `785ae8c` — `feat(import-evidence): add versioned signal promotion projection`
- `07dc759` — `feat(import-evidence): promote qualified aggregate dimensions`
- `0be8930` — `feat(scoring): consume current import evidence projections`
- 当前 HEAD — `test(import-evidence): verify promotion lifecycle and scoring`

## 本阶段完成内容

- 采用方案 B：新增 Import Evidence 专属、版本化 Promotion Ledger 与 active Signal
  Projection；未改变 legacy `company_sources` / `company_signals` 的表结构或语义。
- 新增 corrective Migration `b7f1c84a9d23`，创建：
  `import_evidence_signal_promotions`、`import_evidence_company_signals`、
  `import_evidence_promotion_quality_assessments`。
- Domain、Mapper、Repository Protocol、SQLAlchemy/Fake Repository、UoW、集中 Eligibility
  Policy、Promotion/Query Service、Workflow、Projection Reader 和 Qualification 输入合并已闭环。
- Promotion 可稳定追踪 Aggregate、Shipment Inclusion 和所有参与判断的 current Quality
  Assessment；Source/provider 摘要保存在 JSON provenance，无无必要的第四张来源表。

## Promotion Eligibility 与支持维度

- Aggregate 必须 current、已解析 company、promotable、fingerprint 完整、无 blocker，且
  Inclusion 与 current Quality 可追踪；READY 可评估，PARTIAL 按维度评估，
  INSUFFICIENT_DATA/BLOCKED 不晋级。
- VERIFIED/USABLE 可自动晋级并保留最低质量分；REVIEW/REJECTED 只留 BLOCKED 审计，
  不写 active projection。
- 实际支持 `import_activity`、`china_dependency`、`logistics_complexity`；各维度独立门控。
  未支持 `shipping_fit`（现有字段不足）；明确禁止 cargo value 代理推断、company scale、
  growth、pain point、contactability 和任何 LLM 猜测。
- China ratio 仅使用 known origin 作分母；known=0 时 ratio 为 null，unknown 不按非中国处理。

## 幂等、版本替换与数据所有权

- `(aggregate_id, signal_kind, input_fingerprint)` 保证输入幂等；重跑零新增并保持 stable UUID。
- partial unique indexes 保证每个 company/kind 最多一个 current Promotion 和一个 active
  Import Evidence Signal。新 Aggregate 在同一事务中创建新版本、supersede 旧 Ledger、
  停用旧 Projection；失败完整 rollback，旧 current 保持可用；历史不删除。
- 所有 projection 的 ownership 由列和 Check Constraint 固定为 `import_evidence`，不用字符串
  前缀识别所有权。Company 删除使用 CASCADE，关联表无孤儿。
- Manual/Research Source 和 Signal 只读；Promotion 从不新增、覆盖或删除 legacy 记录。

## Qualification 集成

- Scorer 通过独立 Projection Reader 仅读取 active Import Evidence Signal；inactive/superseded
  不进入评分。集中 Merge Policy 采用 Manual/人工编辑 > VERIFIED/USABLE Import Evidence >
  verified Research，并按质量、新鲜度选择；同 canonical kind 只计一次并记录选择原因。
- 未修改评分权重、70 分阈值、confidence 门槛、Draft/人工审核或邮件发送规则。
- Reader 关闭或失败时 fail-open，原有评分链路继续工作。

## 验证结果

- Stage 4A.4.3 定向测试 29 passed，其中真实 PostgreSQL 集成测试 9 个，覆盖持久化、reload、
  trace、幂等、supersede、唯一约束、rollback、FK、Manual/Research 保护与 Qualification 重算。
- Backend 1038 passed；Ruff PASS；mypy strict 282 files PASS。
- Frontend tsc PASS；ESLint 0 error / 5 个既有 warning；production build PASS。
- E2E 66 passed；flag-off PASS；Migration upgrade/downgrade/upgrade、schema drift 和单 head PASS。
- E2E 隔离库已删除。开发库原业务表行数保持 companies 12、company_sources 27、
  company_signals 99、opportunities 12、opportunity_assessments 18、contacts 12、
  contact_fit_assessments 14、email_drafts 8、research_runs 52；旧/new Import Evidence 表均为 0。
  本轮 Migration 仅创建/删除新增空表，未写入业务数据或 Qualification 历史。

## 尚未开始与禁止事项

- 未开始后续 Stage；未实现 shipping_fit、公开 Promotion API、UI 扩展、批量任务或真实外部数据源。
- 禁止 merge main、创建 tag、自动发送邮件、自动选择联系人、修改 Qualification 权重/门槛，
  或接入真实 ImportYeti/付费来源。
