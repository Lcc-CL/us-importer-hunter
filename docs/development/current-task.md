# Current Task: 阶段 2 封板 + 阶段 3 前端交互

**状态**: 阶段 2 PASS ✅ → 阶段 3 就绪
**分支**: `fix/v0.2.2-internal-trial-findings`
**HEAD**: `e4fb8f3` (已推送 origin)
**日期**: 2026-07-21

## 阶段 2 完成

### ContactSizeProvider
- DeterministicSizeProvider: 从 company signals 推断企业规模
- 识别员工数量、仓库数量、显式规模标记
- 未知 → company_size_fit=5（非惩罚）

### Draft 门禁
- select() 集成至决策人工作流
- review_required=true → Draft 不生成
- selection_result 持久化至 DecisionMakerSelectionOutcome
- 退回兼容: selected_contact 仍正常写入

### A-J 测试矩阵 (17 tests)
A: Procurement Director → Primary ✅
B: 接近候选触发 review ✅
C: 纯销售 → NO_RELEVANT_CONTACT ✅
D: 历史职位 → Rejected ✅
E: Assistant < Buyer ✅
F: 可达性冲突不静默替换 ✅
G: 企业规模适配 ✅
H: 5 次运行稳定 ✅ + 幂等 ✅
I: Primary 生成 Draft / review 不生成 ✅
J: 三家回归 ✅
K: API 契约（6 维度、英文 reason codes、结构校验）✅

### 全量门禁
| 门禁 | 结果 |
|------|------|
| 后端测试 (863) | PASS |
| ruff | PASS |
| mypy strict (249 files) | PASS |
| tsc | PASS |
| eslint | PASS |
| production build | PASS |
| make e2e (66) | PASS |
| make e2e-flag-off | PASS |

## 阶段 3 目标
- 候选联系人 UI（Primary/Alternatives/Supporting/Rejected）
- 人工选择 Primary API
- 联系人切换 + Draft 重新生成
- E2E 测试
- 三家公司浏览器人工复测

## 硬边界
- 不降低评分门槛
- 不合并 main、不创建 tag
- 不实施 LLM 职位分类、海关数据、批量任务、自动发送
