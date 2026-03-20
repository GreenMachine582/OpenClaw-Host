# Discord Integration

Connects OpenClaw to Discord for task ingestion, polls, and status updates via a bot in a single channel.

---

## Setup

### 1. Create a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. New Application → give it a name (e.g. `OpenClaw`)
3. Bot → Reset Token → copy the token
4. Bot → enable **Message Content Intent** and **Server Members Intent**
5. OAuth2 → URL Generator → scopes: `bot`, `applications.commands`
6. Bot permissions: `Send Messages`, `Read Messages/View Channels`, `Add Reactions`, `Embed Links`, `Read Message History`
7. Copy the generated URL, open it in a browser, and add the bot to your server

### 2. Get your channel ID

Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode), then right-click the target channel and copy the ID.

### 3. Configure

```bash
cp integrations/discord/.env.example integrations/discord/.env
```

Fill in `integrations/discord/.env`:

| Variable                | Description                                                                                       |
|-------------------------|---------------------------------------------------------------------------------------------------|
| `DISCORD_BOT_TOKEN`     | Bot token from the Developer Portal                                                               |
| `DISCORD_CHANNEL_ID`    | Channel ID the bot listens and posts in                                                           |
| `DISCORD_ALLOWED_USERS` | Comma-separated Discord user IDs permitted to trigger tasks (optional — leave empty to allow all) |

Update `docker-compose.yml` to load the Discord env file, then rebuild:

```bash
make down
make build
make up
```

---

## Slash Commands

| Command                                    | Description                                            |
|--------------------------------------------|--------------------------------------------------------|
| `/run <task>`                              | Submit a task to the default agent (coder)             |
| `/run <task> agent:<name>`                 | Submit a task to a specific agent                      |
| `/poll <question> <option1> <option2> ...` | Start a poll, agent waits for result before proceeding |
| `/status`                                  | Show current runtime status                            |

---

## Channel Structure

All interaction happens in a single channel. Message types are visually distinguished by embed colour:

| Colour    | Type                         |
|-----------|------------------------------|
| 🔵 Blue   | Task received / in progress  |
| 🟢 Green  | Task complete                |
| 🔴 Red    | Task failed                  |
| 🟡 Yellow | Awaiting input / poll active |
| ⚪ Grey    | Status / informational       |

---

## Polls

Polls are posted as embeds with emoji reactions. The bot waits for the configured duration (`polls.default_duration_seconds`) or until `min_votes_required` is met, then resolves the result and continues the task.

Reactions:
- ✅ — Yes / Approve
- ❌ — No / Reject
- 🤔 — Needs discussion

---

## Permissions

The bot token needs no privileged API access beyond the channel it operates in. Do not grant administrator permissions.

> ⚠️ If the bot token is accidentally committed, reset it immediately in the Discord Developer Portal.
