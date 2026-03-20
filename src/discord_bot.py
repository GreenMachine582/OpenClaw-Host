"""
src/discord_bot.py

Discord bot — slash commands, decision-point notifications, polls.

Discord is NOT a log stream. Posts only at:
  - Task received (acknowledgement)
  - PR opened (human review needed)
  - Poll (human decision needed)
  - Task failed (error requiring attention)
  - /status (on demand)

All intermediate agent output goes to container logs only.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import discord
from discord import app_commands

from src.task_router import VALID_AGENTS, run_pipeline

log = logging.getLogger(__name__)

# ── Embed colours ─────────────────────────────────────────────────────────────

BLUE   = 0x3498db   # Acknowledged / in progress
GREEN  = 0x2ecc71   # PR opened / complete
RED    = 0xe74c3c   # Failed
YELLOW = 0xf1c40f   # Poll / awaiting decision
GREY   = 0x95a5a6   # Status


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_allowed_users() -> set[int]:
    raw = os.environ.get("DISCORD_ALLOWED_USERS", "")
    if not raw.strip():
        return set()
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip()}


def is_allowed(user_id: int) -> bool:
    allowed = get_allowed_users()
    return not allowed or user_id in allowed


def truncate_field(value: str, max_len: int = 1024) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len - 1] + "…"


# ── Bot ───────────────────────────────────────────────────────────────────────

class OpenClawBot(discord.Client):

    def __init__(self, channel_id: int):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.tree = app_commands.CommandTree(self)
        self._start_time = time.time()
        self._active_tasks: dict[str, str] = {}
        self._last_completed: tuple[str, float] | None = None

    async def setup_hook(self):
        guild_id = os.environ.get("DISCORD_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Discord slash commands synced to guild %s", guild_id)
        else:
            await self.tree.sync()
            log.info("Discord slash commands synced globally (may take up to 1 hour)")

    async def on_ready(self):
        log.info("Discord bot ready — logged in as %s", self.user)
        await self.change_presence(activity=discord.Game(name="Waiting for tasks"))

    async def _get_task_channel(self) -> discord.TextChannel | None:
        return super().get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)

    async def post_embed(
        self,
        colour: int,
        title: str,
        fields: dict,
    ) -> discord.Message | None:
        channel = await self._get_task_channel()
        if not channel:
            log.error("Discord channel %d not found", self.channel_id)
            return None
        embed = discord.Embed(title=title, colour=colour, timestamp=datetime.now(timezone.utc))
        for name, value in fields.items():
            embed.add_field(name=name, value=truncate_field(str(value) or "—"), inline=False)
        return await channel.send(embed=embed)

    async def run_pipeline_async(
        self,
        interaction: discord.Interaction,
        task: str,
        agent: str,
    ) -> None:
        task_id = str(interaction.id)
        self._active_tasks[task_id] = task

        # Single acknowledgement — task is running, output goes to logs
        await interaction.followup.send(embed=discord.Embed(
            title="🔵 Task received",
            colour=BLUE,
            timestamp=datetime.now(timezone.utc),
        ).add_field(name="Agent", value=agent, inline=True
        ).add_field(name="Task", value=truncate_field(task), inline=False
        ).add_field(name="Status", value="Running — see logs for progress", inline=False))

        def on_pr_opened(pr_url: str):
            # Post to Discord when repo-manager opens a PR — this is a decision point
            asyncio.get_event_loop().call_soon_threadsafe(
                asyncio.ensure_future,
                self.post_embed(
                    colour=GREEN,
                    title="👀 PR ready for review",
                    fields={
                        "Task": task,
                        "PR": pr_url,
                        "Action": "Review and merge when ready",
                    },
                )
            )

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_pipeline(task=task, agent=agent, on_pr_opened=on_pr_opened),
            )

            self._active_tasks.pop(task_id, None)
            self._last_completed = (task, time.time())

            if not result.success:
                # Post failure — requires attention
                await self.post_embed(
                    colour=RED,
                    title="🔴 Task failed",
                    fields={
                        "Task": task,
                        "Error": result.error or "Unknown error",
                    },
                )
            elif not result.pr_url:
                # Pipeline completed but no PR was opened — only post if no PR
                # (if a PR was opened, on_pr_opened already notified Discord)
                await self.post_embed(
                    colour=GREY,
                    title="✅ Task complete — no PR",
                    fields={
                        "Task": task,
                        "Note": "No code changes were committed. Check logs for output.",
                    },
                )

        except Exception as e:
            self._active_tasks.pop(task_id, None)
            log.exception("Pipeline error: %s", task)
            await self.post_embed(
                colour=RED,
                title="🔴 Task failed",
                fields={"Task": task, "Error": str(e)},
            )


# ── Bot factory ───────────────────────────────────────────────────────────────

def create_bot() -> OpenClawBot:
    channel_id = int(os.environ["DISCORD_CHANNEL_ID"])
    bot = OpenClawBot(channel_id=channel_id)

    # ── /run ──────────────────────────────────────────────────────────────────

    @bot.tree.command(name="run", description="Submit a task to an OpenClaw agent")
    @app_commands.describe(
        task="The task to run",
        agent="Agent to use: coder (default), comms, repo-manager",
    )
    async def run_command(
        interaction: discord.Interaction,
        task: str,
        agent: str = "coder",
    ):
        if not is_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ You are not authorised to submit tasks.", ephemeral=True
            )
            return

        if agent not in VALID_AGENTS:
            await interaction.response.send_message(
                f"❌ Unknown agent `{agent}`. Valid: {', '.join(VALID_AGENTS)}",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        asyncio.create_task(bot.run_pipeline_async(interaction, task, agent))

    # ── /poll ─────────────────────────────────────────────────────────────────

    @bot.tree.command(name="poll", description="Start a poll — use when a decision is needed")
    @app_commands.describe(
        question="The question to put to the team",
        options="Space-separated options (up to 3, default: Yes No)",
    )
    async def poll_command(
        interaction: discord.Interaction,
        question: str,
        options: str = "Yes No",
    ):
        if not is_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ You are not authorised to start polls.", ephemeral=True
            )
            return

        option_list = options.strip().split()[:3]
        emojis = ["✅", "❌", "🤔"][: len(option_list)]
        duration = int(os.environ.get("DISCORD_POLL_DURATION", 300))

        embed = discord.Embed(
            title=f"🟡 Poll: {question}",
            colour=YELLOW,
            timestamp=datetime.now(timezone.utc),
        )
        for emoji, option in zip(emojis, option_list):
            embed.add_field(name=emoji, value=option, inline=True)
        embed.set_footer(text=f"Closes in {duration // 60}m — react to vote")

        await interaction.response.defer()
        channel = await bot._get_task_channel()
        msg = await channel.send(embed=embed)

        for emoji in emojis:
            await msg.add_reaction(emoji)

        await asyncio.sleep(duration)

        msg = await channel.fetch_message(msg.id)
        counts = {r.emoji: r.count - 1 for r in msg.reactions if r.emoji in emojis}
        winner_emoji = max(counts, key=counts.get) if counts else emojis[0]
        winner_option = option_list[emojis.index(winner_emoji)]

        await channel.send(embed=discord.Embed(
            title="🟡 Poll closed",
            colour=YELLOW,
            timestamp=datetime.now(timezone.utc),
        ).add_field(name="Question", value=question, inline=False
        ).add_field(name="Result", value=f"{winner_emoji} {winner_option}", inline=True
        ).add_field(name="Votes", value=str(counts.get(winner_emoji, 0)), inline=True))

    # ── /status ───────────────────────────────────────────────────────────────

    @bot.tree.command(name="status", description="Show OpenClaw runtime status")
    async def status_command(interaction: discord.Interaction):
        uptime_secs = int(time.time() - bot._start_time)
        h, r = divmod(uptime_secs, 3600)
        m, s = divmod(r, 60)

        active = len(bot._active_tasks)
        active_str = truncate_field(
            "\n".join(f"• {t}" for t in bot._active_tasks.values()) or "None"
        )

        if bot._last_completed:
            desc, ts = bot._last_completed
            last_str = truncate_field(f"{desc} ({int(time.time() - ts)}s ago)")
        else:
            last_str = "None"

        await interaction.response.send_message(embed=discord.Embed(
            title="⚪ OpenClaw Status",
            colour=GREY,
            timestamp=datetime.now(timezone.utc),
        ).add_field(name="Uptime", value=f"{h}h {m}m {s}s", inline=True
        ).add_field(name="Active tasks", value=str(active), inline=True
        ).add_field(name="Running", value=active_str, inline=False
        ).add_field(name="Last completed", value=last_str, inline=False))

    return bot


async def start_bot() -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        log.error("DISCORD_BOT_TOKEN not set — Discord bot will not start")
        return
    if not os.environ.get("DISCORD_CHANNEL_ID"):
        log.error("DISCORD_CHANNEL_ID not set — Discord bot will not start")
        return

    bot = create_bot()
    log.info("Starting Discord bot...")
    await bot.start(token)
