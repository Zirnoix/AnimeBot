# cogs/presence.py
from __future__ import annotations
import asyncio
import logging
import discord
from discord.ext import commands, tasks

from modules import core, i18n

LOG = logging.getLogger(__name__)

CYCLE_INTERVAL_HOURS = 3


class Presence(commands.Cog):
    """Présence rotative (Watching) : variantes autour de /help, version, ton dev."""

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
        if not self.bot.is_ready():
            return

        v = getattr(core, "__version__", None) or "dev"
        # Présence globale au bot : textes en français (locale par défaut).
        scenes = i18n.value("presence.scenes", "fr")
        if not isinstance(scenes, list):
            scenes = []
        suffix = i18n.t("presence.version_suffix", "fr", v=v)
        all_scenes = list(scenes) + [suffix]
        if not all_scenes:
            all_scenes = [suffix]
        text = all_scenes[self._idx % len(all_scenes)]
        self._idx += 1
        text = str(text).strip()[:128]

        if text != self._last_text:
            activity = discord.Activity(type=discord.ActivityType.watching, name=text)
            try:
                await self.bot.change_presence(status=discord.Status.online, activity=activity)
            except Exception as e:
                LOG.debug("rotate_presence: change_presence ignorée (%s)", e)
                return
            self._last_text = text

    @rotate_presence.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)


async def setup(bot: commands.Bot):
    await bot.add_cog(Presence(bot))
