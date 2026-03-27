"""
Utility commands for configuration and bot status.

This cog provides utility commands such as uptime, ping, source, and /setchannel.
Owner : panneau **`/owner`** (menu).
"""

from __future__ import annotations

import time

import discord
from discord.ext import commands
from modules import core


class Utils(commands.Cog):
    """Utility commands for bot configuration and status."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.start_time = time.time()

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Affiche la latence du bot."""
        latency = round(self.bot.latency * 1000)  # en ms
        await ctx.send(f"🏓 Pong ! Latence : **{latency} ms**")

    @commands.hybrid_command(name="uptime")
    async def uptime(self, ctx: commands.Context):
        """Affiche depuis combien de temps le bot est en ligne."""
        delta = time.time() - self.start_time
        days = int(delta // 86400)
        hours = int((delta % 86400) // 3600)
        minutes = int((delta % 3600) // 60)
        seconds = int(delta % 60)
        await ctx.send(f"⏳ Uptime : **{days}j {hours}h {minutes}m {seconds}s**")

    @commands.hybrid_command(name="source")
    async def source(self, ctx: commands.Context):
        """Affiche le lien vers le code source du bot."""
        await ctx.send("📦 Code source du bot : https://github.com/Zirnoix/AnimeBot")

    @commands.hybrid_command(name="setchannel")
    @commands.has_permissions(administrator=True)
    async def setchannel(self, ctx: commands.Context) -> None:
        """Définit le salon des annonces « sortie d’épisode » pour ce serveur."""
        try:
            if not ctx.guild:
                await ctx.send("❌ Cette commande doit être utilisée dans un serveur.")
                return
            core.set_guild_alert_channel(ctx.guild.id, ctx.channel.id)
            await ctx.send(
                "✅ Ce salon recevra les **cartes « sortie d’épisode »** pour **ce serveur**.\n"
                "• Liste des animés suivis : **`/airings`** (ex. **`/airings all`** pour les admins).\n"
                "• **Indépendant** du salon du **raid boss** (`/raidconfig`).\n"
                "• Si tu n’as **aucune** annonce alors que la liste est remplie : vérifie les **permissions** du bot "
                "dans ce salon, et que l’API AniList répond (les annonces utilisent la fenêtre après diffusion)."
            )
        except Exception:
            await ctx.send("❌ Une erreur s'est produite lors de la configuration.")

    @commands.hybrid_command(
        name="setlevelupchannel",
        description="Salon des annonces : nouveau titre global (XP) et nouveau titre quiz (paliers score).",
    )
    @commands.has_permissions(administrator=True)
    async def setlevelupchannel(self, ctx: commands.Context) -> None:
        """Les messages « niveau X atteint » vont dans ce salon au lieu du salon où le joueur a gagné l’XP."""
        try:
            if not ctx.guild:
                await ctx.send("❌ Cette commande doit être utilisée dans un serveur.")
                return
            core.set_guild_levelup_channel(ctx.guild.id, ctx.channel.id)
            await ctx.send(
                "✅ Ce salon recevra les **annonces** suivantes (au lieu du salon où la partie a lieu) :\n"
                "• **Nouveau titre global** (XP `/mycard`, `/myrank`) — une annonce par **palier de titre**, pas à chaque niveau.\n"
                "• **Nouveau titre quiz** (score des quiz solo `/animequiz`, `/animequizmulti`) — mêmes paliers que sur la carte.\n"
                "• Pour revenir au comportement par défaut : **`/clearlevelupchannel`**."
            )
        except Exception:
            await ctx.send("❌ Une erreur s'est produite lors de la configuration.")

    @commands.hybrid_command(
        name="clearlevelupchannel",
        description="Supprime le salon dédié aux annonces de niveau XP (comportement par défaut).",
    )
    @commands.has_permissions(administrator=True)
    async def clearlevelupchannel(self, ctx: commands.Context) -> None:
        try:
            if not ctx.guild:
                await ctx.send("❌ Cette commande doit être utilisée dans un serveur.")
                return
            core.clear_guild_levelup_channel(ctx.guild.id)
            await ctx.send(
                "✅ Les montées de niveau XP seront à nouveau annoncées **dans le salon où la partie a lieu** "
                "(ou pas annoncées si l’XP est donnée sans salon)."
            )
        except Exception:
            await ctx.send("❌ Une erreur s'est produite.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Utils(bot))
