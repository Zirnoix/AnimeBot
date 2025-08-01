"""
Miscellaneous utility commands: uptime, alert configuration, reminders,
channel settings and a simple help command.
"""

from __future__ import annotations

from datetime import datetime

import discord
from discord.ext import commands

from ..modules import core


class Utils(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="uptime")
    async def uptime(self, ctx: commands.Context) -> None:
        """Indique depuis combien de temps le bot est actif."""
        # ``bot.uptime_start`` est défini dans ``bot.py`` au démarrage
        start: datetime = getattr(self.bot, "uptime_start", None)
        if not start:
            await ctx.send("⏱️ Uptime non disponible.")
            return
        now = datetime.utcnow()
        delta = now - start
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        desc = f"🕒 **AnimeBot actif depuis :** {hours} heures, {minutes} minutes"
        embed = discord.Embed(title="Uptime du bot", description=desc, color=0x2ecc71)
        await ctx.send(embed=embed)

    @commands.command(name="setalert")
    async def setalert(self, ctx: commands.Context, time_str: str) -> None:
        """Définit l'heure de l'alerte quotidienne (HH:MM)."""
        try:
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError
            prefs = core.load_preferences()
            uid = str(ctx.author.id)
            prefs.setdefault(uid, {})
            prefs[uid]["alert_time"] = f"{hour:02d}:{minute:02d}"
            core.save_preferences(prefs)
            await ctx.send(f"✅ Alerte quotidienne définie à **{hour:02d}:{minute:02d}**.")
        except Exception:
            await ctx.send("❌ Format invalide. Utilise `!setalert HH:MM` (ex: `!setalert 08:30`).")

    @commands.command(name="reminder")
    async def reminder(self, ctx: commands.Context, mode: str = "") -> None:
        """Active ou désactive les rappels d'épisodes imminents."""
        uid = str(ctx.author.id)
        settings = core.load_user_settings()
        settings.setdefault(uid, {})
        if mode.lower() in {"off", "disable", "désactiver"}:
            settings[uid]["reminder"] = False
            core.save_user_settings(settings)
            await ctx.send("🔕 Rappels désactivés pour toi.")
        elif mode.lower() in {"on", "enable", "activer"}:
            settings[uid]["reminder"] = True
            core.save_user_settings(settings)
            await ctx.send("🔔 Rappels activés pour toi.")
        else:
            current = settings.get(uid, {}).get("reminder", True)
            emoji = "🔔" if current else "🔕"
            await ctx.send(f"{emoji} Les rappels sont actuellement **{'activés' if current else 'désactivés'}** pour toi.")

    @commands.command(name="setchannel")
    async def setchannel(self, ctx: commands.Context) -> None:
        """Définit le salon de notifications (réservé au propriétaire)."""
        if ctx.author.id != core.OWNER_ID:
            await ctx.send("🚫 Tu n’as pas la permission d’utiliser cette commande.")
            return
        config = core.get_config()
        config["channel_id"] = ctx.channel.id
        core.save_config(config)
        await ctx.send("✅ Ce canal a été défini pour les notifications.")

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context) -> None:
        """Affiche un message d'aide listant les commandes disponibles."""
        embed = discord.Embed(title="💡 Commandes disponibles", color=discord.Color.blurple())
        embed.add_field(
            name="Épisodes",
            value="`!prochains`, `!next`, `!monnext`, `!planning`, `!monplanning`, `!anitracker`",
            inline=False,
        )
        embed.add_field(
            name="Quiz & Duel",
            value="`!animequiz [difficulté]`, `!animequizmulti [N]`, `!duel @ami`, `!quiztop`, `!myrank`",
            inline=False,
        )
        embed.add_field(
            name="Mini‑jeux",
            value=(
                "`!higherlower`, `!highermean`, `!guessyear`,\n"
                "`!guessepisodes`, `!guessgenre`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Statistiques",
            value="`!mystats`, `!stats <pseudo>`, `!monchart [pseudo]`, `!mycard`",
            inline=False,
        )
        embed.add_field(name="Lien AniList", value="`!linkanilist <pseudo>`, `!unlink`, `!duelstats @ami`", inline=False)
        embed.add_field(
            name="Autres",
            value="`!uptime`, `!setalert HH:MM`, `!reminder on|off`, `!setchannel`",
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utils(bot))