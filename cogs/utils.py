"""
Utility commands for configuration and bot status.

This cog provides utility commands such as uptime check, alert configuration,
reminder settings, and notification channel setup.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import time
import discord
from discord.ext import commands

from modules import core


class Utils(commands.Cog):
    """Utility commands for bot configuration and status."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.start_time = time.time()

    @commands.command(name="ping")
    async def ping(self, ctx):
        """Affiche la latence du bot."""
        latency = round(self.bot.latency * 1000)  # en ms
        await ctx.send(f"🏓 Pong ! Latence : **{latency} ms**")

    @commands.command(name="uptime")
    async def uptime(self, ctx):
        """Affiche depuis combien de temps le bot est en ligne."""
        delta = time.time() - self.start_time
        days = int(delta // 86400)
        hours = int((delta % 86400) // 3600)
        minutes = int((delta % 3600) // 60)
        seconds = int(delta % 60)
        await ctx.send(f"⏳ Uptime : **{days}j {hours}h {minutes}m {seconds}s**")

    @commands.command(name="botinfo")
    async def botinfo(self, ctx):
        """Affiche des infos sur le bot."""
        embed = discord.Embed(
            title="🤖 Infos sur le bot",
            description="Un bot Discord dédié à l’univers des animés, avec AniList, quiz et plus encore !",
            color=discord.Color.blue()
        )
        embed.add_field(name="Créateur", value="**Julien**", inline=True)
        embed.add_field(name="Langage", value="Python", inline=True)
        embed.add_field(name="Librairie", value=f"discord.py {discord.__version__}", inline=True)
        embed.add_field(name="Système", value=platform.system(), inline=True)
        embed.add_field(name="Version Python", value=platform.python_version(), inline=True)
        embed.set_footer(text=f"Demandé par {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="source")
    async def source(self, ctx):
        """Affiche le lien vers le code source du bot."""
        await ctx.send("📦 Code source du bot : [GitHub](https://github.com/Zirnoix/AnimeBot)")


    @commands.command(name="setalert")
    async def setalert(self, ctx: commands.Context, time_str: str) -> None:
        """Définit l'heure de l'alerte quotidienne (HH:MM).

        Example:
            !setalert 08:30
        """
        try:
            # Validation du format de l'heure
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError("Heure invalide")

            # Sauvegarde des préférences
            prefs = core.load_preferences()
            uid = str(ctx.author.id)
            prefs.setdefault(uid, {})
            prefs[uid]["alert_time"] = f"{hour:02d}:{minute:02d}"
            core.save_preferences(prefs)

            await ctx.send(f"✅ Alerte quotidienne définie à **{hour:02d}:{minute:02d}**.")

        except ValueError:
            await ctx.send("❌ Format invalide. Utilise `!setalert HH:MM` (ex: `!setalert 08:30`).")
        except Exception as e:
            await ctx.send("❌ Une erreur s'est produite lors de la configuration.")

    @commands.command(name="reminder")
    async def reminder(self, ctx: commands.Context, mode: Optional[str] = None) -> None:
        """Active ou désactive les rappels d'épisodes.

        Args:
            mode: "on"/"off" pour activer/désactiver les rappels
                 laissez vide pour voir l'état actuel

        Examples:
            !reminder on
            !reminder off
            !reminder
        """
        uid = str(ctx.author.id)
        settings = core.load_user_settings()
        settings.setdefault(uid, {})

        try:
            if mode:
                mode = mode.lower()
                if mode in {"off", "disable", "désactiver"}:
                    settings[uid]["reminder"] = False
                    await ctx.send("🔕 Rappels désactivés pour toi.")
                elif mode in {"on", "enable", "activer"}:
                    settings[uid]["reminder"] = True
                    await ctx.send("🔔 Rappels activés pour toi.")
                else:
                    await ctx.send("❌ Option invalide. Utilise `on` ou `off`.")
                core.save_user_settings(settings)
            else:
                current = settings.get(uid, {}).get("reminder", True)
                emoji = "🔔" if current else "🔕"
                await ctx.send(
                    f"{emoji} Les rappels sont actuellement "
                    f"**{'activés' if current else 'désactivés'}** pour toi."
                )
        except Exception as e:
            await ctx.send("❌ Une erreur s'est produite.")

    @commands.command(name="setchannel")
    @commands.is_owner()
    async def setchannel(self, ctx: commands.Context) -> None:
        """Définit le salon de notifications (réservé au propriétaire)."""
        try:
            config = core.get_config()
            config["channel_id"] = ctx.channel.id
            core.save_config(config)
            await ctx.send("✅ Ce salon a été défini pour les notifications.")
        except Exception as e:
            await ctx.send("❌ Une erreur s'est produite lors de la configuration.")


async def setup(bot):
    await bot.add_cog(Utils(bot))
