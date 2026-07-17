# US Importer Hunter — Codex Instructions

## 项目目标

构建面向国际货运代理的 MVP：

Discovery
→ Company
→ Opportunity
→ Decision Maker
→ Personalized Email Draft
→ Human Review

当前只验证核心闭环，不提前开发商业化高级能力。

## 开始任何任务前必须阅读

1. PROJECT.md
2. docs/architecture.md
3. docs/coding-standard.md
4. docs/decision.md
5. 与当前任务相关的 ADR
6. apps/backend/specs/

不要复制全部文档内容到上下文，只读取与当前任务相关的部分。

## 架构边界

- Domain 不依赖 FastAPI、SQLAlchemy、Redis、OpenAI SDK。
- API Route 不包含业务逻辑。
- Workflow 负责应用层编排。
- Repository 接收和返回 Domain Aggregate，不暴露 ORM Model。
- Provider 不访问 Repository。
- Company 保存事实；Opportunity 保存判断。
- EmailDraft 只生成并等待人工审核，不发送邮件。
- 不修改已冻结的一级目录架构。

## MVP 范围控制

未经明确任务要求，不得新增：

- Kafka、RabbitMQ、Kubernetes、微服务
- Celery
- RAG 或复杂 Memory
- 多 LLM 路由
- 自动邮件发送
- 完整 CRM
- 自动 Follow-up
- 高级 Observability
- 与当前主链无关的抽象

## 质量门禁

完成任务前必须执行：

```bash
cd apps/backend
uv run pytest
uv run ruff check .
uv run mypy app tests --strict
```

涉及数据库时还必须：
在 Docker PostgreSQL 上运行 Migration
验证 upgrade / downgrade / upgrade
运行真实 PostgreSQL 集成测试

工作纪律
开始前先检查 git status 和相关代码。
优先做最小改动，不重构无关模块。
不删除或重写已有 ADR。
不修改历史 Migration；新增 Migration。
遇到偏差必须说明，不能静默改变需求。
先完成测试，再提交。
每个任务一个清晰 Commit。

Review 输出
完成后只输出：
实现摘要
关键文件变化
测试、Ruff、mypy、Migration 结果
Git diff --stat
未解决问题和设计取舍
建议 Commit Message
