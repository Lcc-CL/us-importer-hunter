#!/usr/bin/env bash
# Deploy or update the production stack on this host (any Linux + Docker).
#
#   ./scripts/deploy.sh                # pull main, build, migrate, restart
#   DEPLOY_REF=v0.3.0 ./scripts/deploy.sh   # deploy a tag/branch (rollback)
#   SKIP_PULL=1 ./scripts/deploy.sh    # deploy the current checkout as-is
#
# Env file: .env.production (override with ENV_FILE). See docs/deployment.md.
#
# The body lives in main() so bash parses it completely before `git pull`
# can rewrite this file mid-run.
set -euo pipefail

main() {
  local root env_file ref compose timeout
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cd "$root"

  env_file="${ENV_FILE:-.env.production}"
  ref="${DEPLOY_REF:-main}"
  timeout="${HEALTH_TIMEOUT:-300}"
  compose=(docker compose -f docker-compose.prod.yml --env-file "$env_file")

  if [[ ! -f "$env_file" ]]; then
    echo "error: $env_file not found — copy .env.production.example and fill it in" >&2
    exit 1
  fi

  if [[ "${SKIP_PULL:-0}" != "1" ]]; then
    echo "==> updating checkout to $ref"
    git fetch --tags origin "$ref"
    git checkout -q --detach FETCH_HEAD
  fi
  echo "==> deploying $(git rev-parse --short HEAD)"

  echo "==> building images"
  "${compose[@]}" build

  echo "==> applying database migrations"
  "${compose[@]}" run --rm backend uv run --no-dev alembic upgrade head

  echo "==> starting services"
  "${compose[@]}" up -d --remove-orphans

  echo "==> waiting for health (timeout ${timeout}s)"
  local deadline=$((SECONDS + timeout)) service cid status pending
  while :; do
    pending=""
    for service in backend worker frontend; do
      cid="$("${compose[@]}" ps -q "$service")"
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo missing)"
      [[ "$status" == "healthy" ]] || pending+=" $service=$status"
    done
    [[ -z "$pending" ]] && break
    if (( SECONDS >= deadline )); then
      echo "error: services not healthy:$pending" >&2
      "${compose[@]}" ps >&2
      exit 1
    fi
    sleep 5
  done

  echo "==> deployed $(git rev-parse --short HEAD); all services healthy"
}

main "$@"
