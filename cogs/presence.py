# cogs/presence.py
from __future__ import annotations
import asyncio
import logging
import discord
from discord.ext import commands, tasks

from modules import core

LOG = logging.getLogger(__name__)

# —— CONFIG ——
CYCLE_INTERVAL_HOURS = 3  # rotation du statut toutes les 3 h
# Texte affiché après « Regarde … » (limite Discord ~128 car.). Pas d’emoji obligatoire.
PRESENCE_SCENES = [
    "/help — guide & nouveautés",
    "Toujours en développement — idées bienvenues",
    "Quiz · AniList · sorties · mini-jeux",
    "Boss raid, devinettes, duels… voir /help",
    "Une question ? Commence par /help",
    "Améliorations régulières — restez à l’affût",
    "Lien AniList, rappels, stats : /help",
    "/reportbug — XP bonus (vrai bug)",
    "Bug repéré ? /reportbug",
]

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
        scenes = list(PRESENCE_SCENES) + [f"v{v} · AnimeBot"]
        text = scenes[self._idx % len(scenes)]
        self._idx += 1
        text = text.strip()[:128]

        if text != self._last_text:
            activity = discord.Activity(type=discord.ActivityType.watching, name=text)
            try:
                await self.bot.change_presence(status=discord.Status.online, activity=activity)
            except Exception as e:
                # Souvent après un blocage gateway ou une reconnexion : transport déjà fermé.
                LOG.debug("rotate_presence: change_presence ignorée (%s)", e)
                return
            self._last_text = text

    @rotate_presence.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)

async def setup(bot: commands.Bot):
    await bot.add_cog(Presence(bot))
