# GitHub Integration

Connects OpenClaw to GitHub for repository operations, branch management, and PR creation.

---

## Setup

```bash
cp integrations/github/.env.example integrations/github/.env
```

Fill in `integrations/github/.env`:

| Variable                | Description                                                                    |
|-------------------------|--------------------------------------------------------------------------------|
| `GITHUB_TOKEN`          | Fine-grained personal access token                                             |
| `GITHUB_OWNER`          | Org or username that owns the target repos                                     |
| `GITHUB_DEFAULT_BRANCH` | Base branch for PRs (usually `main`)                                           |
| `GITHUB_PR_REVIEWERS`   | Comma-separated GitHub usernames to auto-request review on every PR (optional) |

Restart the runtime after changing env values:

```bash
docker compose restart openclaw
```

---

## Token Setup

Use a **fine-grained personal access token** — not a classic token.

Generate at: **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**

### Required Permissions

Set the token's resource access to **Only select repositories** and choose the repos OpenClaw will operate on.

Grant the following repository permissions:

| Permission        | Access       | Required for                             |
|-------------------|--------------|------------------------------------------|
| **Metadata**      | Read         | Required by all fine-grained tokens      |
| **Contents**      | Read & write | Clone repos, create and push branches    |
| **Pull requests** | Read & write | Open PRs, request reviewers              |
| **Issues**        | Read & write | Comment on issues (remove if not needed) |

### Do Not Grant

| Permission                        | Reason                                         |
|-----------------------------------|------------------------------------------------|
| **Administration**                | Allows repo settings changes and deletion      |
| **Workflows**                     | Allows triggering and modifying GitHub Actions |
| **Secrets**                       | Allows reading and writing Actions secrets     |
| Any organisation-level permission | Beyond the scope of this agent                 |

> ⚠️ If a token is accidentally committed, revoke it immediately at GitHub → Settings → Developer settings → Personal access tokens and generate a replacement. Assume it is compromised.

---

## Configuration

Non-secret settings live in `config.yml`. Key options:

**`pull_requests.draft`** — set to `true` to open all agent PRs as drafts. Recommended while tuning the agent.

**`pull_requests.reviewers`** — set via `GITHUB_PR_REVIEWERS` in `.env` as a comma-separated list of GitHub usernames. Leave unset to skip auto-review requests.

**`branches.prefix`** — all agent-created branches are namespaced under this prefix. Keeps them identifiable and easy to bulk-delete if needed.

**`pull_requests.labels`** — the `openclaw` label is applied to all agent PRs. Create this label in each target repo for it to apply.

---

## How It's Used

The agent uses this integration to:

- Clone repositories into `sandboxes/repos/`
- Create and push feature branches
- Open pull requests with generated descriptions
- Comment on issues (if Issues permission is granted)

The agent cannot merge PRs, modify repository settings, trigger Actions workflows, or access repos outside the token's resource scope.
