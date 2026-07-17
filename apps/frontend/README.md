# US Importer Hunter frontend

The frontend is one lean Next.js 16 page for the MVP prospect workflow. It can
submit company evidence, display qualification and decision-maker results,
review a generated draft, approve it, and reload the persisted result.

## Local development

```bash
cp .env.example .env.local
npm ci
npm run dev
```

Open <http://localhost:3000>. The backend defaults to
`http://localhost:8000` through `NEXT_PUBLIC_API_BASE_URL`; the value is
centralized in `src/lib/api.ts`. Never put an OpenAI key in frontend variables.

Start the backend and PostgreSQL first when running outside Compose. The backend
can use `EMAIL_GENERATOR_PROVIDER=fake`, which requires no OpenAI key or network
call.

## Quality checks

```bash
./node_modules/.bin/tsc --noEmit
npm run lint
npm run build
```

There is currently no frontend unit/E2E test runner. This MVP uses strict
TypeScript, ESLint, the production build, and a manual Docker browser flow
(Analyze → Refresh → Approve → Refresh) instead of introducing a large test
dependency.

## Page behavior

- `company.sources` supports one or more real source references; two independent
  sources are recommended but never invented.
- `PARTIAL`, `REJECTED`, `RESEARCH_MORE`, and warnings remain typed business
  results rather than generic system errors.
- Successful analysis writes `company_id` to the URL. Reloading that URL reads
  the saved result through `GET /api/v1/mvp/prospects/{company_id}`.
- Approval persists human-review metadata only. No email delivery exists in the
  frontend.
