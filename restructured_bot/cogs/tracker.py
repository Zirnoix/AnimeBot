import discord
from discord.ext import commands

from restructured_bot.modules import core

class Tracker(commands.Cog):
    """Cog pour le suivi d'animés (anitracker) et les notifications utilisateur."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="anitracker")
    async def ani_tracker(self, ctx: commands.Context, sub: str = None, *, title: str = None) -> None:
        """Ajoute ou gère la liste de suivi d'animés de l'utilisateur."""
        user_id = str(ctx.author.id)
        data = core.load_tracker()
        if sub is None:
            # Pas de subcommand : ajouter un anime
            if not title:
                await ctx.send("❌ Utilise : `!anitracker <titre>` pour suivre un anime.")
                return
            # Ajouter un nouvel anime à suivre
            success = core.add_to_tracker(ctx.author.id, title)
            if not success:
                await ctx.send(f"📌 Tu suis déjà **{title}**.")
            else:
                await ctx.send(f"✅ Tu suivras **{title}**. Tu recevras un DM à chaque nouvel épisode.")
        elif sub.lower() == "list":
            series = data.get(user_id, [])
            if not series:
                await ctx.send("📭 Tu ne suis aucun anime.")
            else:
                suivi_list = "\n".join(f"• {s}" for s in series)
                await ctx.send(f"📺 Animés suivis ({len(series)}) :\n{suivi_list}")
        elif sub.lower() == "remove":
            if not title:
                await ctx.send("❌ Utilise : `!anitracker remove <titre>`")
                return
            series = data.get(user_id, [])
            if title in series:
                # Retirer l'anime suivi
                success = core.remove_from_tracker(ctx.author.id, title)
                if success:
                    await ctx.send(f"🗑️ Tu ne suis plus **{title}**.")
                else:
                    await ctx.send(f"❌ Tu ne suivais pas **{title}**.")
            else:
                await ctx.send(f"❌ Tu ne suivais pas **{title}**.")
        else:
            await ctx.send("❌ Utilise : `!anitracker <titre>`, `list` ou `remove <titre>`.")

    @commands.command(name="reminder")
    async def reminder_toggle(self, ctx: commands.Context, mode: str = "") -> None:
        """Active ou désactive les rappels quotidiens (DM)."""
        uid = str(ctx.author.id)
        user_settings = core.load_user_settings()
        user_settings.setdefault(uid, {})
        if mode.lower() in ["off", "disable", "désactiver"]:
            user_settings[uid]["reminder"] = False
            user_settings[uid]["daily_summary"] = False
            core.save_user_settings(user_settings)
            await ctx.send("🔕 Rappels désactivés pour toi.")
        elif mode.lower() in ["on", "enable", "activer"]:
            user_settings[uid]["reminder"] = True
            user_settings[uid]["daily_summary"] = True
            core.save_user_settings(user_settings)
            await ctx.send("🔔 Rappels activés pour toi.")
        else:
            current = user_settings.get(uid, {}).get("reminder", True)
            emoji = "🔔" if current else "🔕"
            await ctx.send(f"{emoji} Les rappels sont actuellement **{'activés' if current else 'désactivés'}** pour toi.")

    @commands.command(name="setalert")
    async def set_alert(self, ctx: commands.Context, time_str: str) -> None:
        """Définit l'heure d'envoi du résumé quotidien des épisodes."""
        try:
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError
        except ValueError:
            await ctx.send("❌ Format invalide. Utilise `!setalert HH:MM` (ex: `!setalert 08:30`).")
            return
        # Sauvegarder l'heure de résumé dans les préférences de l'utilisateur
        uid = str(ctx.author.id)
        prefs = core.load_preferences()
        prefs.setdefault(uid, {})
        prefs[uid]["alert_time"] = f"{hour:02d}:{minute:02d}"
        core.save_preferences(prefs)
        await ctx.send(f"✅ Alerte quotidienne définie à **{hour:02d}:{minute:02d}**.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tracker(bot))
