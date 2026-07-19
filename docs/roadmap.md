# Roadmap

## Sprint 1 — Foundation ✅ (2026-07-15)

- Monorepo scaffold: FastAPI backend (uv, Python 3.12), Next.js 16 frontend
  (TS, Tailwind, shadcn/ui), Docker Compose (backend/frontend/postgres/redis
  + pgAdmin profile), root .env, health endpoints, CI-ready quality gates
  (pytest / ruff / mypy strict / eslint).
- Full layer skeleton: domain, services, agents, tools, providers,
  repositories, prompts (with versioning convention), frontend features.
- No business logic yet — by design.

## Sprint 2 — Data & first vertical slice (proposed)

1. Align open questions: ImportYeti access, LinkedIn policy, scoring model.
2. `Company` / `Contact` models + repositories + first Alembic migration.
3. First tool implementation (data source with lowest legal/technical risk).
4. First end-to-end slice: search → store → list in frontend `companies`.

## Sprint 3 — AI pipeline ✅ (2026-07-17, shipped as v0.1.0 / v0.1.1)

1. Provider interface + OpenAI adapter (email drafts, fake + real).
2. Explainable scoring service + versioned qualification policy.
3. Sales agent (email generation) + `first-outreach-v1` prompt.
4. MVP workflow orchestrating company → opportunity → decision maker → draft.
5. v0.1.1: signal-kind scoring fix, Chinese-default UI, browser E2E suite.

## v0.2 — Website Research Agent (design complete, implementation pending)

Design: [v0.2-research-agent.md](v0.2-research-agent.md) ·
ADR-0025 (research boundary) · ADR-0026 (safe outbound fetching)

The user supplies only a company name and website; the system researches that
website and proposes traceable sources, a profile and standardized signals for
human confirmation before the existing qualification and draft workflow runs.

分两阶段实施：

> **v0.2.0 Internal Beta 已发布（2026-07-19，tag `v0.2.0`）。** 阶段 1 与阶段 2
> 全部完成，十家真实公司验收通过（编造事实 0、evidence 定位率 100%）。
> 验收与门槛修订记录：[validation/v0.2-real-company-evaluation.md](validation/v0.2-real-company-evaluation.md)。

- **阶段 1（已完成）—— 抓取基础设施，不接 LLM、不写前端：**
  `url_guard` → SSRF 测试矩阵 → `SafeFetcher` → 重定向校验 → `robots` →
  `cleaner` → `page_ranker`。不新增数据库表，不改动现有评分/邮件/审批工作流。
- **阶段 2（已完成）—— 领域模型与 LLM：** 四张 `research_*` 表与迁移 →
  抽取器协议（fake + 真实）+ prompt v1 → 校验层 → 研究工作流 → 三个 API 端点
  （含 `POST /api/v1/research/{research_id}/confirm` 人工确认）→ 前端面板 →
  E2E 用例 → 十家公司验收。

**Sprint 1 明确不做：** Google Maps、ImportYeti、LinkedIn、邮箱发现、批量发现、
自动发送、Celery、调度器、多 Agent Planner、无头浏览器渲染。

**v0.2.x 后续（按实测优先级）：** 研究任务异步化（消除同步 45 秒请求）；
在官方 `api.openai.com` 端点上做成本验证（当前门槛基于第三方网关实测，
其 token 计量存在与输入无关的固定底座）；接入海关数据源以支撑
`china_dependency`（官网无法提供，十家中九家维持 Unknown）；把证据提升到
`company_signals`；重新研究与刷新；JS 站点的无头渲染；`reviewer_name` 接入
真实身份系统。

## Later

- Celery (batch research runs), Qdrant + rag service (semantic search),
  additional LLM providers, nginx / flower, auth & multi-tenancy.
