# Anthropic Integration

Connects OpenClaw to the Anthropic API for all agent task execution.

---

## Setup

```bash
cp integrations/anthropic/.env.example integrations/anthropic/.env
```

Fill in `integrations/anthropic/.env`:

| Variable               | Description                                                         |
|------------------------|---------------------------------------------------------------------|
| `ANTHROPIC_API_KEY`    | API key from [console.anthropic.com](https://console.anthropic.com) |
| `ANTHROPIC_MODEL`      | Model ID to use for agent tasks                                     |
| `ANTHROPIC_MAX_TOKENS` | Max tokens per response (default: `4096`)                           |
| `ANTHROPIC_TIMEOUT`    | Request timeout in seconds (default: `60`)                          |

Restart the runtime after changing env values:

```bash
docker compose restart openclaw
```

---

## Model Selection

The default model is `claude-opus-4-6`. Available options:

| Model               | Use case                                                       |
|---------------------|----------------------------------------------------------------|
| `claude-opus-4-6`   | Most capable — recommended for complex coding tasks            |
| `claude-sonnet-4-6` | Faster and cheaper — suitable for simpler or high-volume tasks |

Set via `ANTHROPIC_MODEL` in `.env`.

---

## Configuration

Non-secret settings live in `config.yml`. Key options:

**`model.temperature`** — controls output determinism. Default is `1`. Lower values (e.g. `0.2`) produce more consistent, predictable outputs — useful for code generation tasks.

**`model.max_tokens`** — caps the length of each response. Increase if the agent is truncating long outputs; decrease to reduce cost on lighter tasks.

**`rate_limiting.max_retries`** — number of retry attempts on transient API errors before the task fails.

---

## API Key

Generate or manage keys at: Anthropic Console → API Keys

The key requires no additional scopes — all permissions are account-level.

> ⚠️ If a key is accidentally committed, revoke it immediately at the Anthropic Console and generate a replacement.
