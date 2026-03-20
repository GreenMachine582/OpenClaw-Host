"""
src/discord_bot.py

Discord bot — slash command handler, poll manager, status updates.
Runs alongside the main runtime loop.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import discord
from discord import app_commands

from src.task_router import VALID_AGENTS, run_task

log = logging.getLogger(__name__)

# ── Embed colours ─────────────────────────────────────────────────────────────

BLUE   = 0x3498db   # Task in progress
GREEN  = 0x2ecc71   # Task complete
RED    = 0xe74c3c   # Task failed
YELLOW = 0xf1c40f   # Poll / awaiting input
GREY   = 0x95a5a6   # Status / informational


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_allowed_users() -> set[int]:
    raw = os.environ.get("DISCORD_ALLOWED_USERS", "")
    if not raw.strip():
        return set()
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip()}


def chunk_text(text: str, max_len: int = 1900) -> list[str]:
    """Split text into Discord-safe chunks."""
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at] + "…")
        text = text[split_at:].lstrip()
    chunks.append(text)
    return chunks


def is_allowed(user_id: int) -> bool:
    allowed = get_allowed_users()
    return not allowed or user_id in allowed


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
        self._active_tasks: dict[str, str] = {}   # task_id → description
        self._last_completed: tuple[str, float] | None = None

    async def setup_hook(self):
        self.tree.copy_global_to(guild=None)
        await self.tree.sync()
        log.info("Discord slash commands synced")

    async def on_ready(self):
        log.info("Discord bot ready — logged in as %s", self.user)
        await self.change_presence(activity=discord.Game(name="Waiting for tasks"))

    async def get_channel(self) -> discord.TextChannel | None:
        return self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)

    async def post_embed(self, colour: int, title: str, fields: dict) -> discord.Message | None:
        channel = await self.get_channel()
        if not channel:
            log.error("Discord channel %d not found", self.channel_id)
            return None
        embed = discord.Embed(title=title, colour=colour, timestamp=datetime.now(timezone.utc))
        for name, value in fields.items():
            embed.add_field(name=name, value=value or "—", inline=False)
        return await channel.send(embed=embed)

    async def run_task_async(
        self,
        interaction: discord.Interaction,
        task: str,
        agent: str,
    ) -> None:
        task_id = f"{interaction.id}"
        self._active_tasks[task_id] = task

        # Acknowledge immediately
        await interaction.followup.send(embed=discord.Embed(
            title="🔵 Task received",
            colour=BLUE,
            timestamp=datetime.now(timezone.utc),
        ).add_field(name="Agent", value=agent, inline=True
        ).add_field(name="Task", value=task, inline=False
        ).add_field(name="Status", value="Running...", inline=True))

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: run_task(task=task, agent=agent)
            )

            del self._active_tasks[task_id]
            self._last_completed = (task, time.time())

            # Post result in chunks if needed
            chunks = chunk_text(result)
            channel = await self.get_channel()

            first = discord.Embed(
                title="🟢 Task complete",
                colour=GREEN,
                timestamp=datetime.now(timezone.utc),
            ).add_field(name="Agent", value=agent, inline=True
            ).add_field(name="Task", value=task, inline=False
            ).add_field(name="Response", value=chunks[0], inline=False)
            await channel.send(embed=first)

            for chunk in chunks[1:]:
                await channel.send(embed=discord.Embed(
                    description=chunk, colour=GREEN,
                ))

        except Exception as e:
            self._active_tasks.pop(task_id, None)
            log.exception("Task failed: %s", task)
            channel = await self.get_channel()
            await channel.send(embed=discord.Embed(
                title="🔴 Task failed",
                colour=RED,
                timestamp=datetime.now(timezone.utc),
            ).add_field(name="Agent", value=agent, inline=True
            ).add_field(name="Task", value=task, inline=False
            ).add_field(name="Reason", value=str(e)[:500], inline=False))


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
        asyncio.create_task(bot.run_task_async(interaction, task, agent))

    # ── /poll ─────────────────────────────────────────────────────────────────

    @bot.tree.command(name="poll", description="Start a poll in the channel")
    @app_commands.describe(
        question="The question to ask",
        options="Space-separated options (up to 3)",
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
        duration = 300  # seconds

        embed = discord.Embed(
            title=f"🟡 Poll: {question}",
            colour=YELLOW,
            timestamp=datetime.now(timezone.utc),
        )
        for emoji, option in zip(emojis, option_list):
            embed.add_field(name=emoji, value=option, inline=True)
        embed.set_footer(text=f"Closes in {duration // 60} minutes")

        await interaction.response.defer()
        channel = await bot.get_channel()
        msg = await channel.send(embed=embed)

        for emoji in emojis:
            await msg.add_reaction(emoji)

        await asyncio.sleep(duration)

        msg = await channel.fetch_message(msg.id)
        counts = {r.emoji: r.count - 1 for r in msg.reactions if r.emoji in emojis}
        winner_emoji = max(counts, key=counts.get) if counts else emojis[0]
        winner_option = option_list[emojis.index(winner_emoji)]

        result_embed = discord.Embed(
            title="🟡 Poll closed",
            colour=YELLOW,
            timestamp=datetime.now(timezone.utc),
        ).add_field(name="Question", value=question, inline=False
        ).add_field(name="Result", value=f"{winner_emoji} {winner_option}", inline=True
        ).add_field(name="Votes", value=str(counts.get(winner_emoji, 0)), inline=True)

        await channel.send(embed=result_embed)

    # ── /status ───────────────────────────────────────────────────────────────

    @bot.tree.command(name="status", description="Show OpenClaw runtime status")
    async def status_command(interaction: discord.Interaction):
        uptime_secs = int(time.time() - bot._start_time)
        hours, remainder = divmod(uptime_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        active = len(bot._active_tasks)
        active_str = "\n".join(f"• {t}" for t in bot._active_tasks.values()) or "None"

        if bot._last_completed:
            desc, ts = bot._last_completed
            elapsed = int(time.time() - ts)
            last_str = f"{desc} ({elapsed}s ago)"
        else:
            last_str = "None"

        embed = discord.Embed(
            title="⚪ OpenClaw Status",
            colour=GREY,
            timestamp=datetime.now(timezone.utc),
        ).add_field(name="Uptime", value=uptime_str, inline=True
        ).add_field(name="Active tasks", value=str(active), inline=True
        ).add_field(name="Active", value=active_str, inline=False
        ).add_field(name="Last completed", value=last_str, inline=False)

        await interaction.response.send_message(embed=embed)

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
