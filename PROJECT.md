# US Importer Hunter — Project Document

> The living master document for this project. README.md is the short
> introduction; this file is where vision, scope, architecture and progress
> are tracked. Detailed references live in [docs/](docs/).

## Vision

Freight forwarders win customers through slow, manual prospecting: finding
US importers, judging their shipping volume and lanes, hunting contacts,
writing cold emails. US Importer Hunter turns that into an AI pipeline —
**a sales-intelligence platform that discovers, analyzes and prioritizes
US importers automatically, and drafts the outreach for you.**

## MVP

Three capabilities, one chain:

1. **Search** — find US importers across data sources (customs/BoL data,
   web, company sites).
2. **Analyze** — assess each company as a logistics opportunity (volume,
   lanes, current forwarder, switching signals).
3. **Outreach** — generate personalized outreach emails per company.

Out of scope for MVP: auth/multi-tenancy, email sending infrastructure,
billing. Full scope and open product questions: [docs/prd.md](docs/prd.md).

## Target User

International freight forwarders — sales and business-development roles
prospecting the US import market.

## Architecture

Clean Architecture, monorepo (`apps/backend` FastAPI + `apps/frontend`
Next.js 16):

```
API Routes → Workflows / Services → Agents → Tools → Repositories → Infra
                                       ↓
                                   Providers (LLM vendors, swappable)
Domain: framework-free business entities · Schemas: typed I/O everywhere
```

- **Stack**: FastAPI · Python 3.12 (uv) · PostgreSQL + SQLAlchemy 2.x
  (async) · Redis · Next.js + TypeScript + shadcn/ui · OpenAI SDK.
  Planned: Celery, Qdrant.
- **Key rules**: no business logic in routes; agents never touch the DB;
  all LLM calls via the llm service → provider adapters; typed schemas
  end-to-end; DI everywhere, no global state.
- **Declarative specs**: `apps/backend/specs/*.yaml` is the wiring source
  of truth. **Knowledge base**: `apps/backend/knowledge/` feeds RAG.

Details: [docs/architecture.md](docs/architecture.md) ·
[docs/coding-standard.md](docs/coding-standard.md) ·
[docs/decision.md](docs/decision.md)

## Workflow

Main MVP pipeline (`hunt`):

```
user goal → Planner → Research (fan-out per company, via tools)
          → Scoring service → Sales (email drafts) → Report
```

Agents: planner / research / sales / report. Data sources: ImportYeti,
Google, company websites, LinkedIn (access methods partly TBD).
Details: [docs/workflow.md](docs/workflow.md) · [docs/agents.md](docs/agents.md)

## Sprint

| Sprint | Theme | Status |
|---|---|---|
| 1 | Foundation: scaffold, layers, docs, specs, Docker stack verified | ✅ Done (2026-07-15) |
| 2 | Core domain chain: ingestion, scoring, contact selection, draft generation | ✅ Done (2026-07-16) |
| 3 | Minimal API facade, browser workflow, and v0.1 acceptance | ✅ Done — tag `v0.1.0` (2026-07-17) |
| 3.1 | Signal-kind scoring fix, Chinese-default UI, browser E2E suite | ✅ Done — tag `v0.1.1` (2026-07-19) |
| v0.2 | Website Research Agent — name + website → traceable sources/profile/signals | ✅ Done — tag `v0.2.0` Internal Beta (2026-07-19) |

## Current Progress

**Sprint 1 complete & verified (2026-07-15).** Full skeleton, zero
business logic (by design). Baseline commits: `66217d2` (architecture
v1.0, 167 files) · `c7a0a01` (container-safe settings fix).

- Backend: FastAPI app factory + lifespan DI, async SQLAlchemy + Alembic
  (async env), Redis client, health/readiness endpoints, settings from
  root `.env`. Quality gates green: pytest · ruff · mypy --strict.
- Layers scaffolded (15 modules): domain(4) · agents(4) · tools(5) ·
  providers(4) · services(6) · workflows(4) · repositories · seed ·
  prompts(+shared/+versions) · schemas · shared · events · memory(4) ·
  tasks · observability(3).
- Frontend: Next.js 16 + TS + Tailwind + shadcn/ui, feature-first
  structure (5 features), typed API client. Build & lint green.
- **Infra verified end-to-end in Docker (OrbStack)**: all four compose
  services healthy; readiness probe reports Postgres ✓ Redis ✓; frontend
  serves on :3000, API docs on :8000/docs. pgAdmin available via
  `--profile tools`.
- Docs: 9 topic files + 14 ADRs (docs/ADR/), YAML specs (4), knowledge
  base (7 topic areas), demo seed data (3 companies + 3 contacts).

**Dev environment notes**: Docker Hub pulls go through the host Clash
proxy via OrbStack's relay — if pulls fail with EOF, fully restart
OrbStack (`orbctl stop && orbctl start`), keep `network_proxy auto`,
and retry.

**Top open questions** (block Sprint 2 design): ImportYeti access method ·
LinkedIn compliance approach · scoring dimensions · contact email sourcing.
Full list: [docs/prd.md](docs/prd.md#open-product-questions).

**Sprint 3 browser slice implemented (2026-07-16).** The backend exposes the
three-endpoint MVP facade (analyze, reload, approve), with Fake email generation
as the local default and durable approval metadata. The Next.js root page now
provides one focused prospect form and result workspace: multiple real sources,
optional signals/contact, qualification metrics, decision-maker selection,
review-only draft approval, and URL-based persisted reload. This is intentionally
not a Dashboard, CRM, authentication system, or sending client.

**MVP v0.1 release acceptance in progress (2026-07-16).** The complete Fake
Provider path has passed in Docker through the browser, including qualification,
draft generation, approval, persisted refresh/reload, and exact-replay
idempotency. Backend and frontend quality gates are green, and the local secret
boundary has been tightened so the frontend container does not inherit the root
`.env`. Final acceptance is waiting only for one real OpenAI generation with a
valid local credential; no real call was made with the placeholder value. See
[docs/mvp-acceptance.md](docs/mvp-acceptance.md).

**v0.1.1 released (2026-07-19, tag `v0.1.1`).** Fixed a P0 where the scorer
identified dimensions by English keyword only, so Chinese-language prospects
scored zero on four of eight dimensions, capped below the qualification bar,
and never produced a draft (39.5 → 70.5, REVIEW → QUALIFIED on the reported
company). Shipped alongside it: Chinese-default UI with an English toggle, a
signal-kind dropdown submitting canonical enums, a live provider badge fed by
`GET /api/v1/health/runtime`, and a committed browser E2E suite (`make e2e`,
`make e2e-real`) running against an isolated stack that cannot touch the dev
database. Thresholds, weights, schema, state machine and email gate unchanged.

**v0.2 官网研究 Agent —— 设计已批准，分阶段实施中（2026-07-19）。** 用户只输入
公司名称与官网；系统读取该官网并提出可追溯的 sources、company profile 与标准化
signals —— 每条都携带来源 URL、支撑它的原句和置信度 —— 经人工确认后才进入现有
的资格评估与草稿工作流。研究产出的是 **claim 而非公司事实**：不写 `Company`、
不写 `Opportunity`，现有 analyze 端点仍是进入模型的唯一路径。人工确认通过
`POST /api/v1/research/{research_id}/confirm` 落库，`research_promotions` 表保留
claim 与最终 company signal 的完整追溯关系。网页正文一律视为不可信数据：页面
发现由确定性 `page_ranker` 控制，LLM 不参与选页、不能新增抓取目标。

设计文档：[docs/v0.2-research-agent.md](docs/v0.2-research-agent.md)、
ADR-0025（研究边界与注入防护）、ADR-0026（安全出站抓取 / SSRF 策略）、
ADR-0027（真实抽取器 Provider 边界）。

**v0.2.0 Internal Beta 已发布（2026-07-19，tag `v0.2.0`）。** 十家真实美国进口商
（五金/家具/健身/工业/照明各两家）逐家验收，每家一次 LLM 调用：10/10 安全完成、
evidence 定位率 100%、source URL 验证 100%、**编造事实 0 条**、直接采纳率 85.7%。
W.W. Grainger 从稀薄页面产出 0 条 claim 与 8 个 unknown 维度——无证据时拒绝编造，
正是反幻觉设计的目标行为。验收数据：
[docs/validation/v0.2-real-company-evaluation.md](docs/validation/v0.2-real-company-evaluation.md)。

**已知限制**（完整列表见 [Release Notes](docs/release-notes.md)）：Research API
不得匿名暴露公网；连接级 DNS/IP pinning 未实现；当前经第三方 OpenAI 兼容网关验证，
官方端点未做成本验证；官网无法证明进口记录；多数 `china_dependency` 维持 Unknown；
每条 claim 必须人工审核；不自动发送邮件；JS 重度站点返回 `needs_browser`；
`reviewer_name` 尚未接入真实身份系统。

实施分两阶段：**阶段 1** 为抓取基础设施（url_guard、SafeFetcher、robots、
cleaner、page_ranker），不接 LLM、不写前端、不新增数据库表；**阶段 2** 为四张
`research_*` 表、抽取器、API 与前端。Sprint 1 仅限官网：不含 Google Maps、
ImportYeti、LinkedIn、邮箱发现、批量发现、Celery 与调度器。

## Future Roadmap

- **Complete v0.1 acceptance** — run one real OpenAI draft smoke test using the
  existing adapter, then record the quality decision without retaining the key
  or full sensitive content.
- **Next: real-user trial** — put the evidence → qualification → draft → human
  review loop in front of a small number of freight-forwarder users, collect
  observed blockers, and prioritize only validated workflow improvements.
- **Later backlog** — revisit broader platform capabilities only after the user
  trial establishes a concrete need; architecture expansion is not the next
  milestone.

Details: [docs/roadmap.md](docs/roadmap.md)
