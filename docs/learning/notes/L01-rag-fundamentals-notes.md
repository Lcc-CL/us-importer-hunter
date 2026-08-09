# L01 — RAG Fundamentals Notes

## 我目前的解释

> Leo TODO：用自己的语言填写，不粘贴标准答案。

## 我需要回答的问题

- RAG 系统的检索、上下文构建、生成与引用分别承担什么职责？
- 为什么相似度不能证明事实正确？
- 为什么本项目必须按 `company_id` 隔离公司事实语料？
- 为什么没有证据时应输出 unknown，而不是补全合理事实？
- 为什么 deterministic 主链不应由 RAG 覆盖？

## 本阶段实验

- 对照 R0 架构报告，画出 Import、Research、Opportunity、EmailDraft 的边界图。
- 从现有 Research Claim 中抽取一条证据链，标记 Run、Page、Document 与 Claim 的职责。
- 检查 `RAG_RESEARCH_ENABLED=false` 时，Routing、Opportunity、Draft 行为是否保持原语义。

## 实验结果

- R1 仅建立 cleaned document corpus；未创建 chunk、embedding、vector retrieval 或 reranker。
- Research Claim 仍使用既有 page position 与 evidence snippet 语义。
- 生产配置默认 `RAG_RESEARCH_ENABLED=false`。

## 我理解错的地方

> Leo TODO：记录实验前后的认知修正。

## 面试题

- RAG 与普通 LLM generation 的工程边界是什么？
- 如何保证检索结果不会跨租户或跨 Company 泄漏？
- 为什么离线 evaluation 应早于默认流量切换？
- 什么情况下 deterministic 规则优于 RAG？
- Citation 的可审计性需要哪些稳定标识？

## Leo TODO

- [ ] 完成“我目前的解释”。
- [ ] 回答全部“我需要回答的问题”。
- [ ] 完成边界图与一条证据链实验。
- [ ] 记录至少两条认知修正。
- [ ] 口述回答全部面试题。
