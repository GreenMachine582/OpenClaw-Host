# 🧠 OpenClaw Host

AI agent runtime for code automation and Git workflows, deployed locally via Docker.

OpenClaw operates as a controlled execution environment — not a free-running AI. All changes are PR-driven, filesystem access is restricted to mounted volumes, and outputs are observable at every step.

---

## 📦 Repository Structure

```text
openclaw-host/
├─ docker-compose.yml
├─ Makefile
├─ config/
│  └─ policies/          # allowlist.yml / denylist.yml
├─ prompts/
│  └─ agents/            # coder.md, comms.md, repo-manager.md
├─ integrations/
│  ├─ anthropic/         # .env, config.yml
│  └─ github/            # .env, config.yml
├─ storage/              # Persistent runtime data (not committed)
├─ sandboxes/
│  └─ repos/             # Safe working directories for cloning
├─ scripts/              # Operational helpers
└─ docs/                 # Architecture and runbooks
```

---

## 🚀 Quick Start

```bash
git clone <your-repo>
cd openclaw-host
```

Copy and fill in integration env files:

```bash
cp integrations/anthropic/.env.example integrations/anthropic/.env
cp integrations/github/.env.example integrations/github/.env
```

```bash
sudo make build     # Build Docker images
sudo make up        # Start all services
sudo make onboard   # First-time setup
sudo make logs      # Stream logs
sudo make cli       # Open a shell in the CLI container
sudo make down      # Stop all services
```

---

## 🧠 Agent Roles

| Agent        | File              | Responsibility               |
|--------------|-------------------|------------------------------|
| Coder        | `coder.md`        | Code changes, debugging      |
| Comms        | `comms.md`        | Notifications, summaries     |
| Repo Manager | `repo-manager.md` | Git workflows, PR management |

Prompts live in `prompts/agents/`. The runtime injects values from each integration's `config.yml` into the prompt context at task initialisation — prompts reference these as variables rather than hardcoding values. Output quality is directly tied to prompt quality — refine iteratively.

---

## 🔐 Security Model

| Control      | Recommendation                                  |
|--------------|-------------------------------------------------|
| GitHub Token | Repo-scoped only, no admin rights               |
| Branching    | PR-only — no direct pushes to `main`            |
| Sandboxes    | Always clone into `sandboxes/repos/`            |
| Policies     | Maintain allow/deny rules in `config/policies/` |

The agent has no access to the host filesystem beyond explicitly mounted volumes. Secrets are owned by each integration — there is no root `.env`.

---

## ⚙️ Configuration

Each integration owns its own secrets and config:

- `integrations/anthropic/.env` — API key, model, token limits
- `integrations/anthropic/config.yml` — API settings, sampling parameters
- `integrations/github/.env` — token, owner, reviewers
- `integrations/github/config.yml` — PR behaviour, branch prefix, commit identity

Policy rules:
- `config/policies/allowlist.yml` — permitted commands, paths, and external calls
- `config/policies/denylist.yml` — explicit blocks

---

## 📚 Docs

- [`docs/architecture.md`](docs/architecture.md) — system components, agent model, task loop, policy system
- [`docs/runbooks.md`](docs/runbooks.md) — operational procedures for setup, maintenance, and recovery