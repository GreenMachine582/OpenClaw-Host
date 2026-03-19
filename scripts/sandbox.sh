#!/usr/bin/env bash
# scripts/sandbox.sh
# Manage repo sandboxes — clone, clean, reset, or list.
#
# Usage:
#   ./scripts/sandbox.sh clone <repo-url> [name]
#   ./scripts/sandbox.sh clean <name>
#   ./scripts/sandbox.sh reset <name> [repo-url]
#   ./scripts/sandbox.sh list

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SANDBOX_DIR="sandboxes/repos"
CMD="${1:-}"

usage() {
  echo "Usage:"
  echo "  $0 clone <repo-url> [name]   Clone a repo into the sandbox"
  echo "  $0 clean <name>              Remove a sandbox (keeps directory)"
  echo "  $0 reset <name> [repo-url]   Clean and re-clone"
  echo "  $0 list                      List all sandboxes and their status"
  exit 1
}

require_name() {
  if [ -z "${2:-}" ]; then
    echo -e "${RED}Error:${NC} sandbox name required"
    usage
  fi
}

case "$CMD" in

  clone)
    REPO_URL="${2:-}"
    if [ -z "$REPO_URL" ]; then
      echo -e "${RED}Error:${NC} repo URL required"
      usage
    fi
    NAME="${3:-$(basename "$REPO_URL" .git)}"
    TARGET="$SANDBOX_DIR/$NAME"

    if [ -d "$TARGET/.git" ]; then
      echo -e "${YELLOW}!${NC} $TARGET already exists — skipping clone"
      exit 0
    fi

    mkdir -p "$TARGET"
    echo "Cloning $REPO_URL → $TARGET..."
    git clone "$REPO_URL" "$TARGET"
    echo -e "${GREEN}✓${NC} Cloned $NAME"
    ;;

  clean)
    require_name "$@"
    NAME="$2"
    TARGET="$SANDBOX_DIR/$NAME"

    if [ ! -d "$TARGET" ]; then
      echo -e "${RED}Error:${NC} sandbox '$NAME' not found"
      exit 1
    fi

    echo "Cleaning $TARGET..."
    rm -rf "$TARGET"
    mkdir -p "$TARGET"
    echo -e "${GREEN}✓${NC} Cleaned $NAME"
    ;;

  reset)
    require_name "$@"
    NAME="$2"
    REPO_URL="${3:-}"
    TARGET="$SANDBOX_DIR/$NAME"

    # Try to recover the remote URL if not provided
    if [ -z "$REPO_URL" ] && [ -d "$TARGET/.git" ]; then
      REPO_URL=$(git -C "$TARGET" remote get-url origin 2>/dev/null || true)
    fi

    if [ -z "$REPO_URL" ]; then
      echo -e "${RED}Error:${NC} no repo URL provided and none found in existing sandbox"
      exit 1
    fi

    echo "Resetting $NAME..."
    rm -rf "$TARGET"
    mkdir -p "$TARGET"
    git clone "$REPO_URL" "$TARGET"
    echo -e "${GREEN}✓${NC} Reset $NAME"
    ;;

  list)
    if [ ! -d "$SANDBOX_DIR" ] || [ -z "$(ls -A "$SANDBOX_DIR")" ]; then
      echo "No sandboxes found in $SANDBOX_DIR"
      exit 0
    fi

    printf "%-30s %-40s %-20s\n" "NAME" "REMOTE" "BRANCH"
    printf "%-30s %-40s %-20s\n" "----" "------" "------"

    for dir in "$SANDBOX_DIR"/*/; do
      name=$(basename "$dir")
      if [ -d "$dir/.git" ]; then
        remote=$(git -C "$dir" remote get-url origin 2>/dev/null || echo "—")
        branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "—")
      else
        remote="not a git repo"
        branch="—"
      fi
      printf "%-30s %-40s %-20s\n" "$name" "$remote" "$branch"
    done
    ;;

  *)
    usage
    ;;
esac
