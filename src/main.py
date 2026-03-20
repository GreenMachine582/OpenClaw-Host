"""
OpenClaw runtime entrypoint.

Usage:
    python -m src.main                        # start runtime + Discord bot
    python -m src.main run --task "..."       # submit a one-off task via CLI
    python -m src.main run --task "..." --agent coder
    python -m src.main run --task "..." --dry-run
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import anthropic
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

CONFIG_DIR = Path("/app/config")
INTEGRATIONS_DIR = Path("/app/integrations")


# ── Config ────────────────────────────────────────────────────────────────────

def load_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def validate_env() -> bool:
    required = ["ANTHROPIC_API_KEY", "GITHUB_TOKEN", "GITHUB_OWNER"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        return False
    return True


# ── CLI task runner ───────────────────────────────────────────────────────────

def run_cli_task(task: str, agent: str, dry_run: bool = False) -> None:
    from src.task_router import (
        VALID_AGENTS,
        build_context,
        inject_context,
        load_prompt,
        run_pipeline,
    )

    if agent not in VALID_AGENTS:
        log.error("Unknown agent '%s'. Valid: %s", agent, ", ".join(VALID_AGENTS))
        sys.exit(1)

    print(f"\n── Task ({agent}) ──────────────────────────────────")
    print(task)
    print("────────────────────────────────────────────────\n")

    if dry_run:
        system_prompt = inject_context(load_prompt(agent), build_context())
        print("── System Prompt ────────────────────────────────")
        print(system_prompt)
        print("────────────────────────────────────────────────\n")
        print("[dry-run] No API call made.")
        return

    result = run_pipeline(task=task, agent=agent)

    for step in result.steps:
        print(f"── {step.agent} ──────────────────────────────────")
        print(step.output)
        if step.pr_url:
            print(f"\nPR: {step.pr_url}")
        print("────────────────────────────────────────────────\n")

    if not result.success:
        log.error("Pipeline failed: %s", result.error)
        sys.exit(1)


# ── Runtime ───────────────────────────────────────────────────────────────────

async def run_runtime() -> None:
    log.info("OpenClaw starting...")

    if not validate_env():
        sys.exit(1)

    load_config(INTEGRATIONS_DIR / "anthropic/config.yml")
    load_config(INTEGRATIONS_DIR / "github/config.yml")
    load_config(INTEGRATIONS_DIR / "discord/config.yml")
    log.info("Integration config loaded")

    load_config(CONFIG_DIR / "policies/allowlist.yml")
    load_config(CONFIG_DIR / "policies/denylist.yml")
    log.info("Policies loaded")

    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")
    anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    log.info("Anthropic client initialised (model: %s)", model)

    # Start Discord bot if configured
    discord_task = None
    if os.environ.get("DISCORD_BOT_TOKEN") and os.environ.get("DISCORD_CHANNEL_ID"):
        from src.discord_bot import start_bot
        discord_task = asyncio.create_task(start_bot())
        log.info("Discord bot task started")
    else:
        log.warning("Discord env vars not set — bot disabled")

    shutdown = asyncio.Event()

    def handle_signal():
        log.info("Shutdown signal received")
        shutdown.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    log.info("OpenClaw runtime ready — waiting for tasks")
    await shutdown.wait()

    if discord_task:
        discord_task.cancel()

    log.info("OpenClaw stopped")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="openclaw", description="OpenClaw agent runtime")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Submit a task via CLI")
    run_parser.add_argument("--task", required=True, help="Task description")
    run_parser.add_argument(
        "--agent",
        default="coder",
        choices=["coder", "comms", "repo-manager", "discord-handler"],
        help="Agent to use (default: coder)",
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
        run_cli_task(task=args.task, agent=args.agent, dry_run=args.dry_run)
    else:
        asyncio.run(run_runtime())


if __name__ == "__main__":
    main()
