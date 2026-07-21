# Current Task: 阶段 2 - 多候选决策人六因子评分与选择

**状态**: 阶段 2 核心完成 ✅
**分支**: `fix/v0.2.2-internal-trial-findings`
**HEAD**: `0df6a48` (已推送 origin)
**日期**: 2026-07-21

## 已完成

### 1. SixFactorScorer (六因子评分)
`app/services/contact/scorer.py`
- role_relevance (0-40), seniority (0-15), company_size_fit (0-10)
- import_logistics_fit (0-15), reachability (0-15), source_confidence (0-5)
- 总分上限 100，确定性可重复

### 2. CandidateSelector (多候选选择)
`app/services/contact/selector.py`
- Primary / Alternatives (≤3) / Supporting / Rejected 结构
- review_required 判定（分差≤5、不可达、低置信度）
- 稳定排序（6 级 tie-breaker）
- RejectionReason 枚举（8 种明确拒绝原因）
- SelectionStatus: SELECTED, ALTERNATIVES_AVAILABLE, REVIEW_REQUIRED,
  NO_RELEVANT_CONTACT, NO_REACHABLE_CONTACT

### 3. 持久化
- score_breakdown_json (JSONB NOT NULL DEFAULT '{}')
- selection_status, selection_reasons_json, scoring_version
- Migration roundtrip verified
- 现有 contact_fit_assessments 复用

### 4. API
- DecisionMakerRankingResponse 新增 score_breakdown, selection_status,
  scoring_version, selection_reasons
- 新增 CandidateScoreResponse, DecisionMakerSelectionResponse
- DecisionMakerDetailResponse 新增 selection 字段
- 从已存评估计算，非重新评分

### 5. 后端服务集成
- DeterministicDecisionMakerSelectionService 迁移至 v2 六因子评分
- 向后兼容：rank() 接口不变，role_fit_score 现承载 role_relevance (0-40)
- 新 score_all() 方法返回 CandidateScore 供 selection 使用

### 6. 前端类型
- CandidateScoreResponse, DecisionMakerSelectionResponse 接口
- DecisionMakerRankingResponse 新增 score_breakdown, selection_status 等
- ProspectDetailResponse 新增 selection 字段

## 质量门禁

| 项目 | 结果 |
|------|------|
| 后端测试 (846) | PASS |
| ruff (修改文件) | PASS |
| mypy strict (247 files) | PASS |
| 前端 tsc | PASS |
| 前端 eslint | PASS |
| 前端 production build | PASS |
| make e2e (66 tests) | PASS |
| make e2e-flag-off | PASS |
| migration up/down/up | PASS |

## 未完成 / 留待阶段 3

- Draft Workflow 集成（review_required 阻止 Draft 生成）
- 决策人工作流集成 select() 调用
- 前端 review_required 提示 UI
- 前端联系人切换 UI
- 阶段 2 专项测试矩阵（A-J）
- 三家公司回归（六因子评分验证）
- 企业规模评分提供者（ContactSizeProvider 实现）

## 下一阶段
阶段 3：Draft Workflow 集成 + 前端切换 UI + 专项测试 + 三家回归

## 硬边界
- 不降低资格评分门槛
- 不实施 Primary/Alternatives 前端切换
- 不合并 main、不创建 tag
- 不实施 LLM 职位分类、海关数据、批量任务、自动发送
