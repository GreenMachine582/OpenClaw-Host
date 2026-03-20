"""
src/task_router.py

Routes incoming tasks to the correct agent and returns the response.
Used by both the CLI and Discord bot.
"""

import logging
import os
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

PROMPTS_DIR = Path("/app/prompts/agents")
INTEGRATIONS_DIR = Path("/app/integrations")

VALID_AGENTS = ["coder", "comms", "repo-manager", "discord-handler"]
DEFAULT_AGENT = "coder"


def load_prompt(agent: str) -> str:
    path = PROMPTS_DIR / f"{agent}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text()


def build_context() -> dict:
    """Resolve runtime context variables for prompt injection."""
    import yaml

    def cfg(path):
        p = INTEGRATIONS_DIR / path
        if not p.exists():
            return {}
        with open(p) as f:
            return yaml.safe_load(f) or {}

    github = cfg("github/config.yml")
    discord = cfg("discord/config.yml")

    return {
        "anthropic.model": os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6"),
        "github.branches.prefix": github.get("branches", {}).get("prefix", "openclaw/"),
        "github.branches.base": os.environ.get("GITHUB_DEFAULT_BRANCH", "main"),
        "github.commits.author_name": github.get("commits", {}).get("author_name", "OpenClaw"),
        "github.commits.author_email": github.get("commits", {}).get("author_email", "openclaw@localhost"),
        "github.pull_requests.draft": github.get("pull_requests", {}).get("draft", True),
        "github.pull_requests.labels": github.get("pull_requests", {}).get("labels", ["openclaw"]),
        "github.pull_requests.reviewers": os.environ.get("GITHUB_PR_REVIEWERS", ""),
        "discord.bot.command_prefix": discord.get("bot", {}).get("command_prefix", "/"),
        "discord.messages.max_length": discord.get("messages", {}).get("max_length", 1900),
        "discord.polls.default_duration_seconds": discord.get("polls", {}).get("default_duration_seconds", 300),
        "discord.polls.options_emoji": discord.get("polls", {}).get("options_emoji", ["✅", "❌", "🤔"]),
        "discord.bot.rate_limiting.max_messages_per_minute": discord.get("rate_limiting", {}).get("max_messages_per_minute", 10),
    }


def inject_context(prompt: str, context: dict) -> str:
    for key, value in context.items():
        prompt = prompt.replace("{{" + key + "}}", str(value))
    return prompt


def run_task(task: str, agent: str = DEFAULT_AGENT, stream_callback=None) -> str:
    """
    Run a task through the specified agent.

    Args:
        task: The task description.
        agent: Agent name (coder, comms, repo-manager, discord-handler).
        stream_callback: Optional callable(text_chunk) for streaming output.

    Returns:
        Full response text.
    """
    if agent not in VALID_AGENTS:
        raise ValueError(f"Unknown agent '{agent}'. Valid: {', '.join(VALID_AGENTS)}")

    system_prompt = inject_context(load_prompt(agent), build_context())
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")
    max_tokens = int(os.environ.get("ANTHROPIC_MAX_TOKENS", 4096))

    log.info("Running task via agent=%s model=%s", agent, model)

    full_response = []

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": task}],
    ) as stream:
        for text in stream.text_stream:
            full_response.append(text)
            if stream_callback:
                stream_callback(text)

    result = "".join(full_response)
    log.info("Task complete (agent=%s, chars=%d)", agent, len(result))
    return result
