# ADR-0023：邮件草稿生成与 LLM Provider 边界

- Date: 2026-07-16
- Status: Accepted

## Context

US Importer Hunter MVP 需要根据已评估的 Opportunity 和已选择的 Contact，
生成可供人工审核的个性化英文开发邮件草稿。

## Decision

1. EmailDraft 属于 Outreach Aggregate。
2. 邮件生成与邮件发送完全分离。
3. Workflow 依赖 EmailDraftGenerator 协议，不直接依赖 OpenAI SDK。
4. 本地测试默认使用 FakeEmailDraftGenerator。
5. OpenAI Provider 仅在实际调用时读取并验证 OPENAI_API_KEY。
6. 相同 Context 与 Prompt Version 不重复生成草稿。
7. 新 Context 或新 Prompt Version 创建新草稿版本，不覆盖历史。
8. MVP 只生成 GENERATED 草稿，后续由人工审核。
9. Provider 失败必须回滚当前事务，不影响已完成的上游业务数据。
10. 当前 Prompt 为 first-outreach-v1，仅允许使用 Context 中存在的事实。

## Consequences

- 测试不需要真实网络或 OpenAI Key。
- 后续可以替换其他生成 Provider，而不修改 Domain 和 Workflow。
- 当前不实现邮件发送、自动跟进、多 Provider 路由和复杂事实审计。
