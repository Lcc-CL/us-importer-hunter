# Current Task: 阶段 3 完成 + 阶段 4 设计

**状态**: 阶段 3 PASS ✅ | 阶段 4 设计完成
**分支**: `fix/v0.2.2-internal-trial-findings`
**HEAD**: `558b605` (已推送 origin)
**日期**: 2026-07-21

## 阶段 3 完成

- 候选联系人卡片 UI（Primary/Alternatives/Supporting/Rejected 分组）
- 六因子评分展示（展开/收起）
- 18 个中英文职责标签
- review_required 阻塞提示 + 原因列表
- 人工确认 API（POST .../decision-maker/confirm）
- confirmDecisionMaker 前端 API 客户端
- 服务器端 eligibility 重验证

## 阶段 4 设计完成

### 设计文档
- docs/v0.3-import-evidence-agent.md
- docs/ADR/import-evidence-provider-boundary.md
- docs/ADR/import-entity-resolution.md
- docs/ADR/shipment-deduplication.md
- docs/ADR/import-evidence-quality.md

### 架构决策
- Provider Adapter 模式
- ImportYeti → CID → Datamyne/PIERS 升级路径
- Raw → Normalized → Evidence 三层管道
- 三阶实体解析（强/组合/模糊）
- 双层去重（主键 + 指纹）
- 五维质量评分
- LLM 仅限于商品描述分类和中文摘要

### 阶段 4A 指标
- Fake + ImportYeti provider
- 确定性实体解析
- Master/House BOL 规则
- 证据质量评分
- 全量门禁

## 全量门禁

| 门禁 | 结果 |
|------|------|
| 后端 (863) | PASS |
| ruff | PASS |
| mypy strict (249) | PASS |
| tsc | PASS |
| eslint | PASS |
| production build | PASS |
| make e2e (66) | PASS |
| make e2e-flag-off | PASS |
| migration up/down/up | PASS |
| working tree | clean |
| push | origin synchronized |

## 硬边界
不降低评分阈值、不接真实外部 API（阶段 4 仅设计）、
不合并 main、不创建 tag、不引入 Auth、不自动发送邮件
