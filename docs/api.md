# API

FastAPI app, all routes under `API_V1_PREFIX` (default `/api/v1`).
Interactive docs at `/docs` (disabled in production).

## Conventions

- Routes live in `app/api/routes/`, one module per resource, aggregated
  in `app/api/router.py`.
- Routes contain **no business logic** — validate, delegate to a
  service/workflow, return a typed schema from `app/schemas/`.
- Dependencies come from `app/api/deps.py` (`SettingsDep`, `DbSessionDep`,
  `RedisDep`).
- Errors: raise `HTTPException` in routes only; deeper layers raise
  domain exceptions that routes translate.

## Current endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Liveness — no external dependencies |
| GET | `/api/v1/health/ready` | Readiness — checks PostgreSQL & Redis, reports per-dependency status |
| POST | `/api/v1/mvp/prospects/analyze` | Run the synchronous MVP prospect facade; returns complete, partial or rejected stage outcomes |
| GET | `/api/v1/mvp/prospects/{company_id}` | Reload persisted Company, latest assessment, contacts, decision-maker ranking and drafts |
| POST | `/api/v1/mvp/outreaches/{outreach_id}/drafts/{version}/approve` | Approve one draft version; never sends email |

## MVP prospect facade

The analyze request accepts one company, an optional contact, a sender profile
and `options.generate_email` (default `true`). `company.sources` is a list of
real `{source, reference, retrieved_at?}` provenance records. Each item becomes
an independent `SourceReference` and is ingested through the existing Company
workflow before scoring. API schemas are translated into Discovery/Contact
claim contracts; they are never used as domain entities.

The response contains a stage result for Company, Opportunity, Contact,
decision-maker selection and EmailDraft generation. Business outcomes such as
`RESEARCH_MORE`, `REVIEW`, no contact or a rejected claim return HTTP 200. A
provider failure after upstream persistence returns overall `PARTIAL`.

The conservative scoring policy still requires multiple distinct evidence
sources before `QUALIFIED`. The Swagger example supplies two explicit real
references in one request, allowing the same request to reach the Fake draft
generator when the remaining qualification gates pass. The legacy singular
`company.source` remains accepted only when `company.website` can be used as its
real reference. Callers without a website must migrate to `company.sources`;
the API never invents a provenance reference.

The read endpoint is side-effect free: it neither rescales the Opportunity nor
generates email or domain events. Approval calls the existing Outreach behavior
and persists `approval_status`, `approved_at`, and `approved_by_name` before it
stops. The legacy response names `status` and `approved_by` remain compatibility
aliases. Approval still never sends email.

## Errors and request ids

Errors use `{code, message, request_id}`. Validation maps to 422, missing
resources to 404, invalid domain state to 409, unavailable configured providers
to 503 and unknown failures to a non-leaking 500. Stack traces, database details,
API keys, prompts and provider SDK objects are never returned.

Every response includes `X-Request-ID`; callers may supply the same header.

## Local CORS and email provider

Local CORS permits only `http://localhost:3000` by default through
`BACKEND_CORS_ORIGINS`; wildcard origins are not used. This is an MVP local
configuration, not a production security system.

`EMAIL_GENERATOR_PROVIDER=fake|openai` selects the generator and defaults to
`fake`. OpenAI configuration is validated lazily only if an OpenAI generation is
actually requested. Swagger at `/docs` contains request and response examples.

## Browser client

The single Next.js page at `http://localhost:3000` calls these three MVP routes
through the typed client in `apps/frontend/src/lib/api.ts`. Its backend origin is
configured by `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`); route
components do not construct API URLs. The page preserves typed business results
such as `PARTIAL`, `REJECTED`, and `RESEARCH_MORE`, while HTTP/network failures
show the safe `{code, message, request_id}` envelope.

After analysis, the page stores `company_id` in the URL query. **Refresh result**
and a browser reload both use the read endpoint, including durable
`approval_status`, `approved_at`, and `approved_by_name`. Approval remains human
review only and never calls an email-delivery service.
