# cogs/botinfo.py
from __future__ import annotations
import os
import platform
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

def _format_uptime(delta_seconds: float) -> str:
    s = int(delta_seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}j")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

class BotInfo(commands.Cog):
    """Commande /botinfo avec version, latence, serveurs, uptime, etc."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # timestamp de lancement pour l’uptime
        if not hasattr(self.bot, "_launch_time"):
            self.bot._launch_time = datetime.now(timezone.utc)

    @app_commands.command(name="botinfo", description="Infos sur le bot : version, serveurs, latence, uptime, etc.")
    async def botinfo(self, interaction: discord.Interaction):
        # — Version (ordre de priorité : env > modules.core.__version__ > 'dev')
        version = os.getenv("BOT_VERSION")
        if not version:
            try:
                from modules import core  # si tu as modules/core.py
                version = getattr(core, "__version__", None)
            except Exception:
                version = None
        version = version or "dev"

        guilds = len(self.bot.guilds)
        members = sum((g.member_count or 0) for g in self.bot.guilds)
        ping_ms = round(self.bot.latency * 1000)
        launch = getattr(self.bot, "_launch_time", datetime.now(timezone.utc))
        uptime = _format_uptime((datetime.now(timezone.utc) - launch).total_seconds())

        embed = discord.Embed(
            title="AnimeBot — Informations",
            description="Merci d’utiliser AnimeBot 💙",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Version", value=f"`v{version}`", inline=True)
        embed.add_field(name="Latence", value=f"`{ping_ms} ms`", inline=True)
        embed.add_field(name="Uptime", value=f"`{uptime}`", inline=True)

        embed.add_field(name="Serveurs", value=f"`{guilds}`", inline=True)
        embed.add_field(name="Membres (approx.)", value=f"`{members}`", inline=True)
        embed.add_field(name="Python", value=f"`{platform.python_version()}`", inline=True)

        embed.set_footer(text="Utilise /help pour tout découvrir")
        try:
            if self.bot.user and self.bot.user.display_avatar:
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        except Exception:
            pass

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(BotInfo(bot))
