.PHONY: up up-tools down logs backend frontend infra test lint fmt migrate revision \
        e2e e2e-real e2e-up e2e-down e2e-install e2e-report e2e-flag-off

# --- Docker ---
up:            ## start the full stack
	docker compose up --build

up-tools:      ## start the full stack + pgAdmin
	docker compose --profile tools up --build

down:          ## stop everything (volumes preserved)
	docker compose down

logs:          ## follow logs
	docker compose logs -f

infra:         ## start only postgres + redis (host-run apps)
	docker compose up postgres redis -d

# --- Host development ---
backend:       ## run backend with hot reload on the host
	cd apps/backend && uv run uvicorn app.main:app --reload

frontend:      ## run frontend dev server on the host
	cd apps/frontend && npm run dev

# --- Quality ---
test:          ## backend tests
	cd apps/backend && uv run pytest

lint:          ## backend lint + type check
	cd apps/backend && uv run ruff check . && uv run mypy app

fmt:           ## backend format
	cd apps/backend && uv run ruff format .

# --- Browser E2E (isolated stack: :8001/:3001, throwaway database) ---
e2e-install:   ## install E2E deps + browser (idempotent)
	cd e2e && { [ -f package-lock.json ] && npm ci || npm install; } && \
	  npx playwright install chromium

e2e:           ## full browser regression against the Fake provider (no LLM cost)
	@$(MAKE) e2e-install
	@set -e; ROOT="$$PWD"; \
	  trap 'E2E_PROVIDER=fake "$$ROOT/e2e/scripts/down.sh"' EXIT; \
	  E2E_PROVIDER=fake "$$ROOT/e2e/scripts/up.sh"; \
	  cd "$$ROOT/e2e" && E2E_PROVIDER=fake npx playwright test --grep-invert @real

e2e-real:      ## one real-provider draft check (requires OPENAI_API_KEY; never printed)
	@$(MAKE) e2e-install
	@set -e; ROOT="$$PWD"; \
	  trap 'E2E_PROVIDER=openai "$$ROOT/e2e/scripts/down.sh"' EXIT; \
	  E2E_PROVIDER=openai "$$ROOT/e2e/scripts/up.sh"; \
	  cd "$$ROOT/e2e" && E2E_PROVIDER=openai npx playwright test --grep @real

e2e-up:        ## start the E2E stack and leave it running (debugging)
	./e2e/scripts/up.sh

e2e-down:      ## stop the E2E stack and drop its database
	./e2e/scripts/down.sh

e2e-flag-off:  ## verify the research panel is hidden when its flag is off
	./e2e/scripts/verify-flag-off.sh

e2e-report:    ## open the last HTML report
	cd e2e && npx playwright show-report

# --- Database ---
migrate:       ## apply migrations
	cd apps/backend && uv run alembic upgrade head

revision:      ## create a migration: make revision m="add companies table"
	cd apps/backend && uv run alembic revision --autogenerate -m "$(m)"
