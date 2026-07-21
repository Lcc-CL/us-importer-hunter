# Current Task: Role Taxonomy & 确定性多职责职位识别

**状态**: 阶段 1 完成 ✅
**分支**: `fix/v0.2.2-internal-trial-findings`
**HEAD**: `d73321a` (已推送 origin)
**日期**: 2026-07-20

## 已完成

### 1. Role Taxonomy (集中、版本化)
- 17 个 DecisionRole + unknown，定义在 `app/domain/contact/roles.py`
- 版本标识: `TAXONOMY_VERSION = "decision-role-v1"`
- 每个角色有正/负匹配短语、决策相关度、隐含角色
- `decision_relevance()` 取 max 而非 sum（加角色不能抬高联系人）

### 2. TitleNormalizer
- `app/services/contact/title_normalizer.py`
- 规范大小写、Unicode、&/斜杠/连字符分隔、常见缩写展开
- 识别 seniority (C_LEVEL/VP/DIRECTOR/HEAD/MANAGER/SPECIALIST)
- 识别 former/retired、assistant/associate、interim/acting 标记
- 禁止子字符串误命中（" coo " padded 匹配，防止 coordinator 误判）

### 3. DeterministicRoleMatcher
- `app/services/contact/role_matcher.py`
- 一个职位返回多个 roles[]，含 reasons、confidence、method、taxonomy_version
- 角色隐含链（如 supply_chain → logistics，import → procurement + logistics）

### 4. 已通过的分类案例
- Sales and Purchasing → sales + procurement ✅
- Director of Sales and Procurement → sales + procurement ✅
- Owner / Buyer → ownership + procurement ✅
- Global Supply Manager → sourcing + supply_chain ✅
- Supply Chain and Operations Director → supply_chain + operations + logistics ✅
- Import Compliance Manager → import + compliance ✅
- Inventory and Replenishment Manager → inventory + supply_chain ✅
- Vice President, Purchasing → procurement (不含 ownership) ✅

### 5. 已阻止的误分类
- Important Accounts Manager 不命中 import ✅
- Coordinator 不识别为 C-level ✅
- Former Purchasing Manager 标记为 historical ✅
- Assistant Buyer 低于 Buyer (specialist seniority) ✅
- Independent Sales Agent 不命中 procurement ✅
- 纯 Sales Manager 不命中 procurement/import/logistics ✅

### 6. 生产回归
- HOUSE HASSON: Sales and Purchasing → sales + procurement ✅
- MARATHON: Vice President, Purchasing → procurement + high seniority ✅
- ELITE SALES: Sales Manager → sales only ✅

### 7. 兼容性
- legacy_department 保留（freight 优先投影）
- 新 API 输出 roles[] 和 taxonomy_version
- 旧数据可从 department 恢复单一 roles[]
- 不改变 selected_contact 与 Draft 行为
- 幂等重跑不产生重复 Assessment

### 8. 前后端改动
- 后端: roles.py, values.py, models/contact.py, mappers/contact.py,
  decision_maker.py, mvp.py, e51b7c3d84af 迁移
- 前端: api.ts, i18n.tsx, analysis-result.tsx (roles 徽章)

## 质量门禁

| 项目 | 结果 |
|------|------|
| 后端测试 (846) | PASS |
| ruff (修改文件) | PASS |
| mypy strict (244 文件) | PASS |
| 前端 tsc | PASS |
| 前端 eslint | PASS |
| 前端 production build | PASS |
| make e2e (66 tests) | PASS |
| make e2e-flag-off | PASS |
| 浏览器 console error | 无 |

## 未完成 / 留待阶段 2
- Primary/Alternatives 角色标记（当前所有角色平等）
- LLM 职位分类
- 前端联系人切换
- 海关数据
- 批量任务
- 自动发送

## 继续执行方案（阶段 2）
1. 检查并重跑全部门禁确认基线
2. 研究是否需要 Primary/Alternatives 区分
3. 任何新功能需通过全部质量门禁
4. 保持 working tree clean，推送当前功能分支
