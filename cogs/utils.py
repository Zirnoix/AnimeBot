"""
Utility commands for configuration and bot status.

This cog provides utility commands such as uptime check, alert configuration,
reminder settings, and notification channel setup.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from modules import core


class Utils(commands.Cog):
    """Utility commands for bot configuration and status."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="uptime")
    async def uptime(self, ctx: commands.Context) -> None:
        """Indique depuis combien de temps le bot est actif."""
        start: datetime = getattr(self.bot, "uptime_start", None)
        if not start:
            await ctx.send("⏱️ Uptime non disponible.")
            return

        now = datetime.utcnow()
        delta = now - start
        days, remainder = divmod(int(delta.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Construction du message avec les unités appropriées
        parts = []
        if days > 0:
            parts.append(f"{days} jour{'s' if days > 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} heure{'s' if hours > 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")

        desc = f"🕒 **AnimeBot actif depuis :** {', '.join(parts)}"
        embed = discord.Embed(
            title="Uptime du bot",
            description=desc,
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utils(bot))