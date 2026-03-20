"""
OpenClaw runtime entrypoint.

Loads integration config, validates environment, and starts the agent loop.
Replace the stub loop with real task handling as the agent is built out.
"""

import logging
import os
import signal
import sys
import time

import anthropic
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    if not os.path.exists(path):
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


def main():
    log.info("OpenClaw starting...")

    if not validate_env():
        sys.exit(1)

    # Load integration config
    anthropic_config = load_config("/app/integrations/anthropic/config.yml")
    github_config = load_config("/app/integrations/github/config.yml")
    log.info("Integration config loaded")

    # Load policies
    allowlist = load_config("/app/config/policies/allowlist.yml")
    denylist = load_config("/app/config/policies/denylist.yml")
    log.info("Policies loaded")

    # Initialise Anthropic client
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")
    log.info("Anthropic client initialised (model: %s)", model)

    # Graceful shutdown
    shutdown = {"flag": False}

    def handle_signal(sig, frame):
        log.info("Shutdown signal received")
        shutdown["flag"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    log.info("OpenClaw runtime ready — waiting for tasks")

    # Stub loop — replace with real task ingestion (webhook, queue, CLI trigger)
    while not shutdown["flag"]:
        time.sleep(5)

    log.info("OpenClaw stopped")


if __name__ == "__main__":
    main()
