# cogs/presence.py
from __future__ import annotations
import asyncio
import discord
from discord.ext import commands, tasks

# —— CONFIG ——
CYCLE_INTERVAL_HOURS = 6  # mets 12 pour un cycle 2x par jour
PRESENCE_SCENES = [
    "/help ✨",                   # → "Regarde /help ✨"
    "les commandes sur /help 🎮", # → "Regarde les commandes sur /help 🎮"
    "/help pour commencer 🚀",    # → "Regarde /help pour commencer 🚀"
]

class Presence(commands.Cog):
    """Présence rotative autour du /help."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._idx = 0
        self._last_text: str | None = None

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.rotate_presence.is_running():
            self.rotate_presence.start()

    @tasks.loop(hours=CYCLE_INTERVAL_HOURS)
    async def rotate_presence(self):
        if not self.bot.is_ready() or not PRESENCE_SCENES:
            return

        text = PRESENCE_SCENES[self._idx % len(PRESENCE_SCENES)]
        self._idx += 1
        text = text.strip()[:128]

        if text != self._last_text:
            activity = discord.Activity(type=discord.ActivityType.watching, name=text)
            await self.bot.change_presence(status=discord.Status.online, activity=activity)
            self._last_text = text

    @rotate_presence.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)

async def setup(bot: commands.Bot):
    await bot.add_cog(Presence(bot))
