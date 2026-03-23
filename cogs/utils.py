"""
Utility commands for configuration and bot status.

This cog provides utility commands such as uptime, ping, source, and /setchannel.
Owner debug commands (test alerte, salon notifications) are under `/admin`.
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
        """Définit le salon de notifications (réservé au propriétaire)."""
        try:
            config = core.get_config()
            config["channel_id"] = ctx.channel.id
            core.save_config(config)
            await ctx.send(
                "✅ Ce salon est enregistré pour les **notifications** (alertes, etc.). "
                "La **liste du serveur** pour `/next` se gère avec **`/airings`**."
            )
        except Exception:
            await ctx.send("❌ Une erreur s'est produite lors de la configuration.")


class BotAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="setavatar")
    @commands.is_owner()
    async def set_avatar(self, ctx: commands.Context):
        """Change l'avatar du bot avec l'image attachée au message."""
        if not ctx.message.attachments:
            return await ctx.send("❌ Envoie l'image **dans le même message** que la commande.")
        try:
            avatar_bytes = await ctx.message.attachments[0].read()
            await self.bot.user.edit(avatar=avatar_bytes)
            await ctx.send("✅ Avatar du bot mis à jour avec succès !")
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")


async def setup(bot: commands.Bot):
    # Un seul setup qui ajoute les deux cogs
    await bot.add_cog(Utils(bot))
    await bot.add_cog(BotAdmin(bot))
