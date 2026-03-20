"""
src/task_router.py

Runs tasks through an agent pipeline:
  coder → repo-manager (creates PR)

Discord is notified only at decision points:
  - Task received
  - PR opened (awaiting review)
  - Poll/approval needed
  - Error

All intermediate agent output goes to logs only.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import anthropic
import yaml

log = logging.getLogger(__name__)

PROMPTS_DIR = Path("/app/prompts/agents")
INTEGRATIONS_DIR = Path("/app/integrations")

VALID_AGENTS = ["coder", "comms", "repo-manager", "discord-handler"]
DEFAULT_AGENT = "coder"

# Pipeline: maps the triggering agent to the sequence that follows
PIPELINE: dict[str, list[str]] = {
    "coder": ["coder", "repo-manager"],
    "comms": ["comms"],
    "repo-manager": ["repo-manager"],
    "discord-handler": ["discord-handler"],
}


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    agent: str
    output: str
    pr_url: str | None = None


@dataclass
class PipelineResult:
    task: str
    steps: list[AgentResult] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def pr_url(self) -> str | None:
        for step in reversed(self.steps):
            if step.pr_url:
                return step.pr_url
        return None

    @property
    def final_output(self) -> str:
        return self.steps[-1].output if self.steps else ""


# ── Config ────────────────────────────────────────────────────────────────────

def _cfg(path: str) -> dict:
    p = INTEGRATIONS_DIR / path
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def build_context() -> dict:
    github = _cfg("github/config.yml")
    discord = _cfg("discord/config.yml")
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


def load_prompt(agent: str) -> str:
    path = PROMPTS_DIR / f"{agent}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text()


def inject_context(prompt: str, context: dict) -> str:
    for key, value in context.items():
        prompt = prompt.replace("{{" + key + "}}", str(value))
    return prompt


# ── Single agent call ─────────────────────────────────────────────────────────

def _run_agent(
    agent: str,
    messages: list[dict],
    context: dict,
) -> str:
    """Call a single agent. Returns full response text. Logs output, no Discord."""
    system_prompt = inject_context(load_prompt(agent), context)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")
    max_tokens = int(os.environ.get("ANTHROPIC_MAX_TOKENS", 4096))

    log.info("Agent %s starting...", agent)
    chunks = []

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)

    result = "".join(chunks)
    log.info("Agent %s complete (%d chars)", agent, len(result))
    log.debug("Agent %s output:\n%s", agent, result)
    return result


def _extract_pr_url(text: str) -> str | None:
    """Pull a GitHub PR URL out of agent output if present."""
    import re
    match = re.search(r"https://github\.com/[^\s\)\"]+/pull/\d+", text)
    return match.group(0) if match else None


# ── Pipeline runner ───────────────────────────────────────────────────────────

def run_pipeline(
    task: str,
    agent: str = DEFAULT_AGENT,
    on_pr_opened: Callable[[str], None] | None = None,
) -> PipelineResult:
    """
    Run a task through the full agent pipeline.

    Args:
        task: The task description.
        agent: Entry-point agent — determines which pipeline runs.
        on_pr_opened: Optional callback(pr_url) called when repo-manager opens a PR.
                      Use this to post a Discord notification.

    Returns:
        PipelineResult with all step outputs and the PR URL if created.
    """
    if agent not in VALID_AGENTS:
        raise ValueError(f"Unknown agent '{agent}'. Valid: {', '.join(VALID_AGENTS)}")

    pipeline = PIPELINE.get(agent, [agent])
    context = build_context()
    result = PipelineResult(task=task)

    # Conversation history passed between agents
    messages: list[dict] = [{"role": "user", "content": task}]

    try:
        for step_agent in pipeline:
            output = _run_agent(step_agent, messages, context)
            pr_url = _extract_pr_url(output)
            result.steps.append(AgentResult(agent=step_agent, output=output, pr_url=pr_url))

            # Append agent output to conversation so next agent has full context
            messages.append({"role": "assistant", "content": output})

            # Notify Discord only when a PR is opened — a human decision point
            if pr_url and on_pr_opened:
                log.info("PR opened: %s", pr_url)
                on_pr_opened(pr_url)

    except Exception as e:
        result.error = str(e)
        log.exception("Pipeline failed at agent=%s task=%r", agent, task)

    return result


# ── CLI convenience wrapper ───────────────────────────────────────────────────

def run_task(task: str, agent: str = DEFAULT_AGENT) -> PipelineResult:
    """Thin wrapper for CLI use — no Discord callbacks."""
    return run_pipeline(task=task, agent=agent)
