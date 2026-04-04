"""
Utility commands for configuration and bot status.

This cog provides utility commands such as uptime, ping, source, and /setchannel.
Owner : panneau **`/owner`** (menu).
"""

from __future__ import annotations

import time

import discord
from discord.ext import commands
from modules import core, i18n


class Utils(commands.Cog):
    """Utility commands for bot configuration and status."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.start_time = time.time()

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Affiche la latence du bot."""
        lg = i18n.ctx_lang(ctx)
        latency = round(self.bot.latency * 1000)  # en ms
        await ctx.send(i18n.t("utils.ping", lg, latency=latency))

    @commands.hybrid_command(name="uptime")
    async def uptime(self, ctx: commands.Context):
        """Affiche depuis combien de temps le bot est en ligne."""
        lg = i18n.ctx_lang(ctx)
        delta = time.time() - self.start_time
        days = int(delta // 86400)
        hours = int((delta % 86400) // 3600)
        minutes = int((delta % 3600) // 60)
        seconds = int(delta % 60)
        await ctx.send(
            i18n.t("utils.uptime", lg, days=days, hours=hours, minutes=minutes, seconds=seconds)
        )

    @commands.hybrid_command(name="source")
    async def source(self, ctx: commands.Context):
        """Affiche le lien vers le code source du bot."""
        lg = i18n.ctx_lang(ctx)
        await ctx.send(i18n.t("utils.source", lg))

    @commands.hybrid_command(name="setchannel")
    @commands.has_permissions(administrator=True)
    async def setchannel(self, ctx: commands.Context) -> None:
        """Définit le salon des annonces « sortie d’épisode » pour ce serveur."""
        lg = i18n.ctx_lang(ctx)
        try:
            if not ctx.guild:
                await ctx.send(i18n.t("utils.need_guild", lg))
                return
            core.set_guild_alert_channel(ctx.guild.id, ctx.channel.id)
            await ctx.send(i18n.t("utils.setchannel_ok", lg))
        except Exception:
            await ctx.send(i18n.t("utils.config_err", lg))

    @commands.hybrid_command(
        name="setlevelupchannel",
        description="Salon des annonces : nouveau titre global (XP) et nouveau titre quiz (paliers score).",
    )
    @commands.has_permissions(administrator=True)
    async def setlevelupchannel(self, ctx: commands.Context) -> None:
        """Les messages « niveau X atteint » vont dans ce salon au lieu du salon où le joueur a gagné l’XP."""
        lg = i18n.ctx_lang(ctx)
        try:
            if not ctx.guild:
                await ctx.send(i18n.t("utils.need_guild", lg))
                return
            core.set_guild_levelup_channel(ctx.guild.id, ctx.channel.id)
            await ctx.send(i18n.t("utils.setlevelup_ok", lg))
        except Exception:
            await ctx.send(i18n.t("utils.config_err", lg))

    @commands.hybrid_command(
        name="clearlevelupchannel",
        description="Supprime le salon dédié aux annonces de niveau XP (comportement par défaut).",
    )
    @commands.has_permissions(administrator=True)
    async def clearlevelupchannel(self, ctx: commands.Context) -> None:
        lg = i18n.ctx_lang(ctx)
        try:
            if not ctx.guild:
                await ctx.send(i18n.t("utils.need_guild", lg))
                return
            core.clear_guild_levelup_channel(ctx.guild.id)
            await ctx.send(i18n.t("utils.clearlevelup_ok", lg))
        except Exception:
            await ctx.send(i18n.t("utils.clearlevelup_err", lg))


async def setup(bot: commands.Bot):
    await bot.add_cog(Utils(bot))
