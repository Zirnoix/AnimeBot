from datetime import datetime
import discord
from discord.ext import commands

from restructured_bot.modules import core

class System(commands.Cog):
    """Cog pour les commandes utilitaires du bot (système)."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="uptime")
    async def uptime(self, ctx: commands.Context) -> None:
        """Indique depuis combien de temps le bot est en ligne."""
        if hasattr(self.bot, "uptime_start"):
            delta = datetime.now(core.TIMEZONE) - self.bot.uptime_start
        else:
            # Si l'attribut n'existe pas, on considère delta inconnu
            await ctx.send("ℹ️ Le temps d'activité du bot est indisponible.")
            return
        # Convertir delta en jours, heures, minutes
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        msg = "🕒 Bot actif depuis "
        if days: 
            msg += f"{days} jour(s), "
        msg += f"{hours} heure(s), {minutes} minute(s)."
        await ctx.send(msg)

    @commands.command(name="setchannel")
    async def set_channel(self, ctx: commands.Context) -> None:
        """Définit le canal actuel comme canal des notifications globales."""
        if ctx.author.id != core.OWNER_ID:
            await ctx.send("🚫 Tu n’as pas la permission d’utiliser cette commande.")
            return
        config = core.get_config()
        config["channel_id"] = ctx.channel.id
        core.save_config(config)
        await ctx.send("✅ Ce salon a été défini comme canal des notifications du bot.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(System(bot))
