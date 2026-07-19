#!/usr/bin/env bash
# Bring up the isolated E2E stack: throwaway database, migrations, containers,
# then wait until both tiers actually answer.
#
#   E2E_PROVIDER=fake|openai  (default: fake)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

E2E_PROVIDER="${E2E_PROVIDER:-fake}"
E2E_DB="${E2E_DB:-importer_hunter_e2e}"
POSTGRES_USER="${POSTGRES_USER:-app}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.e2e.yml)
# Local HTTP proxies (Clash and friends) hijack localhost; always bypass.
CURL=(curl -sS --noproxy '*')

export E2E_PROVIDER E2E_DB

if [ "$E2E_PROVIDER" = "openai" ]; then
  # Presence check only — the value is never printed or logged.
  key="${OPENAI_API_KEY:-}"
  if [ -z "$key" ] && [ -f .env ]; then
    key="$(grep -E '^OPENAI_API_KEY=' .env | cut -d= -f2- | tr -d '"'"'"'' || true)"
  fi
  if [ -z "$key" ]; then
    echo "ERROR: real mode requires OPENAI_API_KEY (shell env or root .env)." >&2
    exit 1
  fi
  echo "Real provider mode: credential present (value not shown)."
fi

echo "==> starting shared infrastructure (postgres, redis)"
"${COMPOSE[@]}" up -d postgres redis

echo "==> waiting for postgres"
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> recreating throwaway database: $E2E_DB"
"${COMPOSE[@]}" exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS $E2E_DB WITH (FORCE)" >/dev/null
"${COMPOSE[@]}" exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
  -c "CREATE DATABASE $E2E_DB" >/dev/null

echo "==> applying migrations to $E2E_DB"
"${COMPOSE[@]}" run --rm --no-deps backend-e2e uv run alembic upgrade head >/dev/null

echo "==> starting backend-e2e (:8001) and frontend-e2e (:3001) · provider=$E2E_PROVIDER"
"${COMPOSE[@]}" up -d --build backend-e2e frontend-e2e

echo "==> waiting for backend"
for _ in $(seq 1 60); do
  if "${CURL[@]}" -o /dev/null http://localhost:8001/api/v1/health 2>/dev/null; then break; fi
  sleep 2
done
"${CURL[@]}" -o /dev/null http://localhost:8001/api/v1/health

echo "==> waiting for frontend"
for _ in $(seq 1 90); do
  if "${CURL[@]}" -o /dev/null http://localhost:3001 2>/dev/null; then break; fi
  sleep 2
done
"${CURL[@]}" -o /dev/null http://localhost:3001

actual="$("${CURL[@]}" http://localhost:8001/api/v1/health/runtime)"
echo "==> E2E stack ready · runtime: $actual"
