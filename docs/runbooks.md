# Runbooks

Operational procedures for the OpenClaw runtime. Each runbook is self-contained — follow steps in order and check expected output before proceeding.

<!-- TOC -->
* [Runbooks](#runbooks)
  * [1. Start / Stop the Stack](#1-start--stop-the-stack)
  * [2. First-Time Onboarding](#2-first-time-onboarding)
  * [3. Trigger a Task Manually](#3-trigger-a-task-manually)
  * [4. Add a New Repository Sandbox](#4-add-a-new-repository-sandbox)
  * [5. Rotate API Keys / Tokens](#5-rotate-api-keys--tokens)
    * [Anthropic API Key](#anthropic-api-key)
    * [GitHub Token](#github-token)
  * [6. Update Agent Prompts](#6-update-agent-prompts)
  * [7. Update Policies](#7-update-policies)
  * [8. Recover from a Failed Task](#8-recover-from-a-failed-task)
  * [9. Clear Session State](#9-clear-session-state)
  * [10. View and Export Logs](#10-view-and-export-logs)
  * [11. Upgrade OpenClaw](#11-upgrade-openclaw)
<!-- TOC -->

---

## 1. Start / Stop the Stack

```bash
make up      # Start all services
make down    # Stop all services (volumes preserved)
```

Verify services are running:

```bash
docker compose ps
```

All containers should show `Up`. If any show `Exit`, check logs before proceeding.

Restart a single service:

```bash
docker compose restart openclaw
```

---

## 2. First-Time Onboarding

Run once after cloning and configuring `.env`.

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY and GITHUB_TOKEN at minimum
make up
make onboard
```

Onboarding validates environment variables, initialises `storage/`, and confirms API connectivity.

**If it fails, check:**
- No trailing whitespace around values in `.env`
- `GITHUB_TOKEN` has `repo` scope
- Outbound access to `api.anthropic.com` and `api.github.com` is not blocked

---

## 3. Trigger a Task Manually

```bash
make cli
```

Opens a shell inside the `openclaw-cli` container. From there:

```bash
openclaw run --task "your task description here"
```

Manual tasks follow the same policy and sandbox rules as automated ones. Exit when done:

```bash
exit
```

---

## 4. Add a New Repository Sandbox

> ⚠️ The `sandboxes/` directory is created by Docker on first run and may be root-owned. Fix permissions before proceeding:
> ```bash
> sudo chown -R $USER:$USER sandboxes/
> ```

**Step 1 — Clone the repo into the sandbox:**

```bash
make sandbox-clone URL=https://github.com/your-org/<repo-name> NAME=<repo-name>
```

Or manually:

```bash
mkdir -p sandboxes/repos/<repo-name>
git clone https://github.com/your-org/<repo-name> sandboxes/repos/<repo-name>
```

**Step 2 — Add the repo to the allowlist** (`config/policies/allowlist.yml`):

```yaml
repositories:
  - github.com/your-org/<repo-name>
```

**Step 3 — Verify token access:**

```bash
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/your-org/<repo-name>
```

Expected: `200 OK`. A `403` or `404` means the token lacks access.

**Step 4 — Restart the runtime:**

```bash
docker compose restart openclaw
```

**List all sandboxes:**

```bash
make sandbox-list
```

---

## 5. Rotate API Keys / Tokens

### Anthropic API Key

1. Generate a new key at [console.anthropic.com](https://console.anthropic.com)
2. Update `.env`: `ANTHROPIC_API_KEY=new_key`
3. `docker compose restart openclaw`
4. Revoke the old key

### GitHub Token

1. Generate a new token (scope: `repo` only)
2. Update `.env`: `GITHUB_TOKEN=new_token`
3. `docker compose restart openclaw`
4. Revoke the old token

> ⚠️ If a key is accidentally committed, rotate it immediately — assume it is compromised.

---

## 6. Update Agent Prompts

Prompts live in `prompts/agents/`. Edits take effect on the next task — no restart required.

Test changes with a dry run before using in live workflows:

```bash
make cli
openclaw run --task "describe what you would do to fix a failing test" --dry-run
```

Review the planned output before allowing execution. Commit prompt changes with a note on what behaviour you were tuning.

---

## 7. Update Policies

Edit `config/policies/allowlist.yml` or `denylist.yml`, then restart:

```bash
docker compose restart openclaw
```

Verify the policy loaded:

```bash
make logs
```

Look for `policies loaded` in startup output. If you see a parse error, revert and check YAML syntax.

---

## 8. Recover from a Failed Task

**Step 1 — Check logs:**

```bash
make logs
```

Look for `ERROR` or `TASK_FAILED`. Note the task ID if present.

**Step 2 — Inspect the sandbox:**

```bash
git -C sandboxes/repos/<repo-name> status
git -C sandboxes/repos/<repo-name> log --oneline -5
```

**Step 3 — Retry or clean up:**

To retry:
```bash
make cli
openclaw run --task "<original task>"
```

If the sandbox is in a bad state:
```bash
rm -rf sandboxes/repos/<repo-name>
mkdir sandboxes/repos/<repo-name>
```

The agent re-clones on the next run.

---

## 9. Clear Session State

Clear if the agent is carrying stale context between runs.

```bash
make down
rm -rf storage/sessions/*
make up
```

To also clear the active workspace:

```bash
rm -rf storage/workspace/*
```

Logs and task history in `storage/data/` and `storage/logs/` are not affected.

---

## 10. View and Export Logs

```bash
make logs                              # Stream live logs
docker compose logs openclaw           # Service-specific logs
docker compose logs openclaw > out.txt # Export to file
```

Logs are also written persistently to `storage/logs/`. Prune old files if disk usage grows:

```bash
find storage/logs/ -name "*.log" -mtime +30 -delete
```

---

## 11. Upgrade OpenClaw

**Step 1 — Back up storage:**

```bash
cp -r storage/ storage-backup-$(date +%Y%m%d)/
```

**Step 2 — Pull and restart:**

```bash
docker compose pull
make down
make up
```

**Step 3 — Verify:**

```bash
docker compose ps
make logs
```

If the upgrade breaks something, restore and restart:

```bash
make down
cp -r storage-backup-<date>/ storage/
make up
```