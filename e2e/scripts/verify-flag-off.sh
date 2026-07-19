#!/usr/bin/env bash
# Verify the research panel is absent when the feature flag is off.
#
# This cannot be an ordinary Playwright test: Next.js inlines NEXT_PUBLIC_*
# at build time, so one running frontend has one fixed value. The E2E stack
# runs with the flag ON to exercise the panel; this script starts a second,
# throwaway frontend with the flag OFF and asserts the panel never reaches the
# HTML. Default-off is a security property, so it is checked, not assumed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PORT="${FLAG_OFF_PORT:-3002}"
NAME="uih-frontend-flagoff"
CURL=(curl -sS --noproxy '*')

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> starting a frontend with NEXT_PUBLIC_ENABLE_RESEARCH unset (:$PORT)"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  -e NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \
  -p "$PORT:3000" \
  -v "$REPO_ROOT/apps/frontend/src:/app/src" \
  us-importer-hunter-frontend-e2e >/dev/null

echo "==> waiting for it to serve"
for _ in $(seq 1 60); do
  if "${CURL[@]}" -o /dev/null "http://localhost:$PORT" 2>/dev/null; then break; fi
  sleep 2
done

html="$("${CURL[@]}" "http://localhost:$PORT")"

if grep -q 'data-testid="research-panel"' <<<"$html"; then
  echo "FAIL: the research panel rendered with the flag off" >&2
  exit 1
fi
if grep -q '内部测试功能' <<<"$html"; then
  echo "FAIL: the internal-testing notice rendered with the flag off" >&2
  exit 1
fi

# Sanity check: the page itself did render, so the assertion above is
# meaningful rather than passing on an error page.
if ! grep -q '潜在客户分析工作台' <<<"$html"; then
  echo "FAIL: the page did not render at all — the check above proves nothing" >&2
  exit 1
fi

echo "PASS: flag off → no research panel, and the rest of the page still renders"
