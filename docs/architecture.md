# Architecture Overview

OpenClaw Host is a Docker-based runtime that runs an AI agent in a controlled local environment. This document covers how the system is structured and how its components interact.

---

## System Diagram

```
┌──────────────────────────────────────────────┐
│                 Host Machine                 │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │           Docker Network               │  │
│  │                                        │  │
│  │  ┌─────────────┐   ┌───────────────┐   │  │
│  │  │  openclaw   │   │ openclaw-cli  │   │  │
│  │  │  (runtime)  │   │ (task runner) │   │  │
│  │  └──────┬──────┘   └───────────────┘   │  │
│  │         │                              │  │
│  │  ┌──────▼───────────────────────────┐  │  │
│  │  │         Mounted Volumes          │  │  │
│  │  │  config/  prompts/  sandboxes/   │  │  │
│  │  │  storage/  integrations/         │  │  │
│  │  └──────────────────────────────────┘  │  │
│  └────────────────────────────────────────┘  │
│                      │                       │
└──────────────────────┼───────────────────────┘
                       │ Outbound only
              ┌────────┴────────┐
              ▼                 ▼
        Anthropic API      GitHub API
```

---

## Components

### Runtime Container (`openclaw`)

The core long-running service. Connects to the Anthropic API, loads agent prompts from `prompts/agents/`, applies policy rules from `config/policies/`, and executes tasks against mounted sandboxes.

All state lives in the `storage/` volume — the container itself is stateless.

### CLI Container (`openclaw-cli`)

A short-lived container for one-off operations: onboarding, reconfiguration, and manual task triggers. Shares the same volumes as the runtime.

### Sandboxes

All repository operations happen inside `sandboxes/repos/`. The agent clones repos here, makes changes, and runs tests. This is the only place external code is executed.

The boundary is enforced at the volume mount level — the runtime has no access to the host filesystem beyond explicitly declared mounts.

### Storage

```text
storage/
├─ data/       # Persisted task history
├─ logs/       # Structured application logs
├─ workspace/  # Files actively being worked on
└─ sessions/   # Agent session state
```

Not committed to version control. Back up separately if session continuity matters.

---

## Agent Roles

Each role is a Markdown prompt file in `prompts/agents/` defining the agent's responsibilities, constraints, and output format.

| Role         | File              | Responsibility                               |
|--------------|-------------------|----------------------------------------------|
| Coder        | `coder.md`        | Code analysis, modification, debugging       |
| Comms        | `comms.md`        | Notifications, summaries                     |
| Repo Manager | `repo-manager.md` | Branch strategy, PR creation, Git operations |

A task may invoke multiple roles in sequence. Roles are loaded at task initialisation and can be edited without restarting the runtime.

---

## Task Execution Loop

```
1. Receive task (webhook, CLI trigger, or scheduled job)
2. Load agent role + policy context
3. Plan — decompose into steps
4. Execute — run steps using available tools (shell, filesystem, Git, HTTP)
5. Validate — check output, run tests
6. Iterate or exit
```

---

## Policy System

Policies in `config/policies/` govern what the agent can do at runtime.

```yaml
# allowlist.yml
commands:
  - git
  - pytest
paths:
  - sandboxes/repos/
external:
  - api.github.com
```

```yaml
# denylist.yml
commands:
  - rm -rf
paths:
  - /home/
  - /etc/
```

Requests outside the allowlist or matching the denylist are blocked and logged.

---

## Security Boundaries

| Boundary         | Enforcement                                  |
|------------------|----------------------------------------------|
| Host filesystem  | Docker volume mounts only                    |
| External network | Outbound only; domains governed by allowlist |
| GitHub access    | Token scoped to target repos, no admin       |
| Code execution   | Sandboxes only                               |