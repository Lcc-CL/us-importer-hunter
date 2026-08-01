#!/usr/bin/env bash
# Tear the E2E stack down and destroy its database. The shared postgres/redis
# containers and the dev stack are deliberately left running.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

E2E_DB="${E2E_DB:-importer_hunter_e2e}"
POSTGRES_USER="${POSTGRES_USER:-app}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.e2e.yml)

echo "==> removing E2E containers"
"${COMPOSE[@]}" rm -sf backend-e2e worker-e2e frontend-e2e >/dev/null 2>&1 || true

echo "==> dropping database $E2E_DB"
"${COMPOSE[@]}" exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS $E2E_DB WITH (FORCE)" >/dev/null 2>&1 || true

remaining="$("${COMPOSE[@]}" exec -T postgres psql -U "$POSTGRES_USER" -d postgres -tAX \
  -c "SELECT count(*) FROM pg_database WHERE datname = '$E2E_DB'" 2>/dev/null | tr -d '[:space:]')"
echo "==> teardown complete · ${E2E_DB} rows in pg_database: ${remaining:-unknown}"
