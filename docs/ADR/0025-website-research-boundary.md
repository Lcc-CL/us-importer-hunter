# ADR-0025 — 官网研究产出可审核的 claim，而非公司事实

状态：**已批准（设计），待分阶段实施**（v0.2，分支 `feat/v0.2-research-agent`）
日期：2026-07-19
相关：ADR-0018（discovery 只产出事件）、ADR-0019（claim → company 摄取）、
ADR-0023（邮件草稿生成边界）、ADR-0026（安全出站抓取）

## 背景

v0.2 新增一个读取公司官网的 agent，产出 sources、profile 与标准化 signals。
写代码之前必须先定三件事：

1. 研究产物落在哪里 —— 直接进 `Company` 聚合，还是别处？
2. 产品要求每条 signal 携带来源 URL、证据片段与置信度。但今天的
   `company_signals` 是 `(company_id, position, signal TEXT)`，扁平字符串，
   三者都无处安放。
3. 网页正文由第三方控制，可能包含针对我们 LLM 的指令。这类内容的信任级别是
   什么？

ADR-0018 已经为 discovery 回答过同形问题：discovery 产出的是 **claim**，只有
Company 上下文才把 claim 变成事实。研究是同一形状的问题，只是换了输入源。

## 决策

### 1. 研究产出提案，绝不产出公司事实

研究端点不创建也不修改 `Company`、`Opportunity` 或任何评分产物，只返回研究
结果。只有显式的人工确认才会把结果送入现有
`POST /api/v1/mvp/prospects/analyze`，后者仍是进入公司与机会模型的唯一路径。
评分、决策人选择、草稿生成与审批完全不受影响。

### 2. 证据保存在四张独立的 research 表中

```
research_runs         运行状态、时间、计数、抽取器 provider/model/prompt 版本
research_pages        每个抓取页面的 URL、最终 URL、状态码、字节数、截断标记
research_claims       kind、detail、evidence_snippet、来源页外键、置信度、校验状态
research_promotions   claim ↔ company signal 的追溯关系（见第 3 条）
```

人工确认后，被接受的 claim 以今天的 `"kind: detail"` 字符串形式提升进
`company_signals`，被接受的页面提升为 `company_sources`。

### 3. `research_promotions` 闭合追溯链

该表记录 `research_claim_id`、`company_id`、最终 `company_signal_position`、
`decision`（`accepted` / `rejected` / `edited`）、`reviewed_at` 与
`edited_detail`。

被拒绝的 claim **同样入表**。这是唯一能回答"抽取器提出了什么、人实际采纳了
什么"的数据来源，也是后续校准置信度等级与度量抽取精度的基础。当 `decision`
为 `edited` 时，`research_claims` 中的原始 claim 保持不变，人改写的文本存在
`edited_detail` —— 我们同时保留机器的原始主张与人的最终判断。

### 4. 人工确认是独立端点

`POST /api/v1/research/{research_id}/confirm` 接受逐条 claim 的
accept / reject / edit 决定与页面选择，写入 `research_promotions`，并返回可
直接填充现有 prospect 表单的载荷。该端点**不调用 analyze、不创建公司**。
`company_id` 与 `company_signal_position` 在用户随后真正提交 analyze 之后回填。

### 5. 无可定位证据的 claim 一律丢弃

以下三种情况在代码中**丢弃**该 claim，而不是降低其置信度：`kind` 不在八个
标准枚举内；`source_url` 不属于本次实际抓取的 URL 集合；`evidence_snippet`
无法在其引用页面的清洗正文中定位。**prompt 中的约束不视为强制手段。**

### 6. 网页正文是不可信数据

页面内容永远是数据，永远不是指令。具体保障：

- **页面发现完全由确定性 `page_ranker` 控制**，LLM 不参与选页、不决定抓取
  目标、不能新增 URL；
- 抓取目标集合在调用 LLM **之前**冻结，抽取阶段不发起任何网络请求；
- 页面文本在 prompt 中以明确分隔符包裹并标注为不可信；
- 强制 JSON 模式 + 严格 schema 校验，代码层只读取 schema 内字段；
- 系统 prompt 与凭据不与页面内容同域流转，也从不出现在响应中；
- 检测到注入特征时记录 warning 并在审核界面标注该页面。

结构性结论：由于选页确定、目标冻结、且 `source_url` 必须命中已抓取集合，
即便注入成功，其最大影响也只是产出会被第 5 条丢弃的垃圾 claim —— 无法访问新
目标、无法泄露凭据、无法改变抓取行为。

### 7. 抽取器位于协议之后，并提供 fake 实现

`ResearchExtractor` 与 `EmailDraftGenerator`（ADR-0023）同构：领域协议、用于
测试与演示的确定性 fake、以及 provider 支撑的真实实现。provider SDK 类型不
越过边界。这保证 `make e2e` 仍可零 LLM 成本运行。

## 备选方案

**给 `company_signals` 加 `source_url`、`evidence_snippet`、`confidence`
三列。** 长期更优：证据会永久随 signal 存在，而不是隔一次 join。本阶段拒绝，
因为它修改评分器读取的表，进而牵动 `Company` 聚合、mapper、迁移与评分输入 ——
正是本阶段被明确禁止改写的部分。排入 v0.2.x，待研究产出被证明值得长期保留。

**研究结果直接写入 `Company`，事后由人清理。** 拒绝：会把未经审核的机器产出
写进权威模型，而现有模型没有"未确认事实"这一状态，也违背 ADR-0018 对 claim
与事实的区分。

**发出 `CompanyDiscovered` 事件复用 `CompanyIngestionWorkflow`。** 有吸引力，
后续大概率正确。本阶段拒绝：该路径会立即创建公司，早于任何人看到证据，
直接抵消产品要求的确认闸门。

## 后果

**好处。** 现有工作流零风险。证据完整留存 —— 哪一页、哪一句、多大把握、人是否
采纳。审核采纳数据从第一天开始积累，可用真实行为校准置信度。fake 抽取器让
`make e2e` 保持免费。注入的爆炸半径被结构性限制。

**代价。** 提升后的 `company_signals` 行仍无内联证据，追溯需经
`research_promotions` 一次 join。signal 存在两种表示（research claim 与提升后的
字符串），人工编辑会让二者不同 —— 这是有意的，`edited_detail` 明确记录差异。

**接受的取舍。** Sprint 1 研究为同步执行（范围内不引入 Celery），一次运行最多
占用一个请求 45 秒。转异步是 v0.2.x 的第一项。
