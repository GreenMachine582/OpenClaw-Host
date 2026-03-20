"""
OpenClaw runtime entrypoint.

Usage:
    python -m src.main                        # start the long-running runtime
    python -m src.main run --task "..."       # submit a one-off task
    python -m src.main run --task "..." --agent coder
    python -m src.main run --task "..." --dry-run
"""

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

import anthropic
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

PROMPTS_DIR = Path("/app/prompts/agents")
CONFIG_DIR = Path("/app/config")
INTEGRATIONS_DIR = Path("/app/integrations")

DEFAULT_AGENT = "coder"
VALID_AGENTS = ["coder", "comms", "repo-manager"]


# ── Config ────────────────────────────────────────────────────────────────────

def load_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_prompt(agent: str) -> str:
    path = PROMPTS_DIR / f"{agent}.md"
    if not path.exists():
        log.error("Prompt file not found: %s", path)
        sys.exit(1)
    return path.read_text()


def validate_env() -> bool:
    required = ["ANTHROPIC_API_KEY", "GITHUB_TOKEN", "GITHUB_OWNER"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        return False
    return True


def build_context() -> dict:
    """Resolve runtime context variables injected into agent prompts."""
    github = load_config(INTEGRATIONS_DIR / "github/config.yml")
    return {
        "anthropic.model": os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6"),
        "github.branches.prefix": github.get("branches", {}).get("prefix", "openclaw/"),
        "github.branches.base": os.environ.get("GITHUB_DEFAULT_BRANCH", "main"),
        "github.commits.author_name": github.get("commits", {}).get("author_name", "OpenClaw"),
        "github.commits.author_email": github.get("commits", {}).get("author_email", "openclaw@localhost"),
        "github.pull_requests.draft": github.get("pull_requests", {}).get("draft", True),
        "github.pull_requests.labels": github.get("pull_requests", {}).get("labels", ["openclaw"]),
        "github.pull_requests.reviewers": os.environ.get("GITHUB_PR_REVIEWERS", ""),
    }


def inject_context(prompt: str, context: dict) -> str:
    """Replace {{variable}} placeholders in a prompt with resolved values."""
    for key, value in context.items():
        prompt = prompt.replace("{{" + key + "}}", str(value))
    return prompt


# ── Task runner ───────────────────────────────────────────────────────────────

def run_task(task: str, agent: str, dry_run: bool = False) -> None:
    if agent not in VALID_AGENTS:
        log.error("Unknown agent '%s'. Valid agents: %s", agent, ", ".join(VALID_AGENTS))
        sys.exit(1)

    system_prompt = inject_context(load_prompt(agent), build_context())

    print(f"\n── Task ({'dry-run' if dry_run else agent}) ──────────────────────────")
    print(task)
    print("────────────────────────────────────────────────\n")

    if dry_run:
        print("── System Prompt ────────────────────────────────")
        print(system_prompt)
        print("────────────────────────────────────────────────\n")
        print("[dry-run] No API call made.")
        return

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")
    max_tokens = int(os.environ.get("ANTHROPIC_MAX_TOKENS", 4096))

    log.info("Sending task to %s via %s...", agent, model)

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": task}],
    ) as stream:
        print("── Response ─────────────────────────────────────")
        for text in stream.text_stream:
            print(text, end="", flush=True)
        print("\n────────────────────────────────────────────────\n")

    log.info("Task complete")


# ── Runtime loop ──────────────────────────────────────────────────────────────

def run_runtime() -> None:
    log.info("OpenClaw starting...")

    if not validate_env():
        sys.exit(1)

    load_config(INTEGRATIONS_DIR / "anthropic/config.yml")
    load_config(INTEGRATIONS_DIR / "github/config.yml")
    log.info("Integration config loaded")

    load_config(CONFIG_DIR / "policies/allowlist.yml")
    load_config(CONFIG_DIR / "policies/denylist.yml")
    log.info("Policies loaded")

    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")
    anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    log.info("Anthropic client initialised (model: %s)", model)

    shutdown = {"flag": False}

    def handle_signal(sig, frame):
        log.info("Shutdown signal received")
        shutdown["flag"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    log.info("OpenClaw runtime ready — waiting for tasks")

    while not shutdown["flag"]:
        time.sleep(5)

    log.info("OpenClaw stopped")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="openclaw", description="OpenClaw agent runtime")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Submit a task to an agent")
    run_parser.add_argument("--task", required=True, help="Task description")
    run_parser.add_argument(
        "--agent",
        default=DEFAULT_AGENT,
        choices=VALID_AGENTS,
        help=f"Agent to use (default: {DEFAULT_AGENT})",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved prompt without calling the API",
    )

    args = parser.parse_args()

    if args.command == "run":
        if not validate_env():
            sys.exit(1)
        run_task(task=args.task, agent=args.agent, dry_run=args.dry_run)
    else:
        run_runtime()


if __name__ == "__main__":
    main()
