#!/usr/bin/env bash
# scripts/health.sh
# Checks the runtime health of the OpenClaw stack.
# Exits 0 if healthy, 1 if any check fails.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

EXIT=0

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; EXIT=1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

echo "=== OpenClaw Health Check ==="
echo ""

# --- Docker services ---
echo "Services:"
services=(openclaw)
for service in "${services[@]}"; do
  status=$(docker compose ps --format json 2>/dev/null \
    | python3 -c "import sys,json; rows=[json.loads(l) for l in sys.stdin if l.strip()]; \
      match=[r for r in rows if '$service' in r.get('Name','')]; \
      print(match[0].get('State','unknown') if match else 'not found')" 2>/dev/null || echo "unknown")
  if [ "$status" = "running" ]; then
    pass "$service is running"
  else
    fail "$service is $status"
  fi
done

# --- Required directories ---
echo ""
echo "Storage:"
dirs=(storage/data storage/logs storage/workspace storage/sessions sandboxes/repos)
for dir in "${dirs[@]}"; do
  if [ -d "$dir" ]; then
    pass "$dir exists"
  else
    fail "$dir missing"
  fi
done

# --- Disk usage ---
echo ""
echo "Disk:"
usage=$(du -sh storage/ 2>/dev/null | cut -f1)
pass "storage/ usage: $usage"

sandbox_usage=$(du -sh sandboxes/ 2>/dev/null | cut -f1)
pass "sandboxes/ usage: $sandbox_usage"

# Warn if storage is over 1GB
storage_kb=$(du -sk storage/ 2>/dev/null | cut -f1)
if [ "$storage_kb" -gt 1048576 ]; then
  warn "storage/ exceeds 1GB — consider pruning logs or archiving sessions"
fi

# --- Env files ---
echo ""
echo "Configuration:"
if [ -f .env ]; then
  pass ".env present"
else
  fail ".env missing — run 'make onboard'"
fi

for integration in anthropic github; do
  env_file="integrations/${integration}/.env"
  if [ -f "$env_file" ]; then
    pass "$env_file present"
  else
    warn "$env_file missing — run 'make onboard' or copy from .env.example"
  fi
done

# --- Policy files ---
for policy in config/policies/allowlist.yml config/policies/denylist.yml; do
  if [ -f "$policy" ]; then
    pass "$policy present"
  else
    fail "$policy missing"
  fi
done

# --- Sandbox status ---
echo ""
echo "Sandboxes:"
sandbox_count=$(find sandboxes/repos -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
if [ "$sandbox_count" -eq 0 ]; then
  warn "No sandboxes found — add repos with './scripts/sandbox.sh clone <url>'"
else
  pass "$sandbox_count sandbox(s) present"
  for dir in sandboxes/repos/*/; do
    name=$(basename "$dir")
    if [ -d "$dir/.git" ]; then
      branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
      dirty=$(git -C "$dir" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
      if [ "$dirty" -gt 0 ]; then
        warn "$name — branch: $branch, uncommitted changes: $dirty file(s)"
      else
        pass "$name — branch: $branch, clean"
      fi
    else
      warn "$name — not a git repo"
    fi
  done
fi

# --- Result ---
echo ""
if [ "$EXIT" -ne 0 ]; then
  echo -e "${RED}Health check failed — see errors above.${NC}"
  exit 1
fi
echo -e "${GREEN}All checks passed.${NC}"
