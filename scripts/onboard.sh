#!/usr/bin/env bash
# scripts/onboard.sh
# First-time setup: validates environment, initialises directories, checks connectivity.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; EXIT=1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

EXIT=0

echo "=== OpenClaw Onboarding ==="
echo ""

# --- Integration env files and required vars ---
echo "Checking integration env files..."

declare -A required_vars
required_vars[anthropic]="ANTHROPIC_API_KEY"
required_vars[github]="GITHUB_TOKEN GITHUB_OWNER"

for integration in "${!required_vars[@]}"; do
  env_file="integrations/${integration}/.env"
  example_file="integrations/${integration}/.env.example"

  if [ ! -f "$env_file" ]; then
    if [ -f "$example_file" ]; then
      cp "$example_file" "$env_file"
      warn "Copied $example_file → $env_file (fill in values)"
    else
      fail "Missing $env_file and no .env.example found"
      continue
    fi
  else
    pass "$env_file exists"
  fi

  for var in ${required_vars[$integration]}; do
    val=$(grep -E "^${var}=" "$env_file" | cut -d= -f2 | tr -d '[:space:]')
    if [ -z "$val" ] || [ "$val" = "your_key_here" ] || [ "$val" = "your_token_here" ]; then
      fail "$var is not set in $env_file"
    else
      pass "$var is set"
    fi
  done
done

# --- Directory initialisation ---
echo ""
echo "Initialising directories..."

dirs=(
  storage/data
  storage/logs
  storage/workspace
  storage/sessions
  sandboxes/repos
)

for dir in "${dirs[@]}"; do
  if [ ! -d "$dir" ]; then
    mkdir -p "$dir"
    pass "Created $dir"
  else
    pass "$dir exists"
  fi
done

# --- Result ---
echo ""
if [ "$EXIT" -ne 0 ]; then
  echo -e "${RED}Onboarding failed — fix the errors above and re-run.${NC}"
  exit 1
fi

pass "Onboarding complete. Run 'make up' to start the stack."
