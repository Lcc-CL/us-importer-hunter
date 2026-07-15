.PHONY: up up-tools down logs backend frontend infra test lint fmt migrate revision

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

# --- Database ---
migrate:       ## apply migrations
	cd apps/backend && uv run alembic upgrade head

revision:      ## create a migration: make revision m="add companies table"
	cd apps/backend && uv run alembic revision --autogenerate -m "$(m)"
