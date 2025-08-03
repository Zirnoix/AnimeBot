# restructured_bot/cogs/stats.py

import discord
from discord.ext import commands
from restructured_bot.modules import anilist, database, core, image

class AniListStats(commands.Cog):
    """Affiche les statistiques d’un utilisateur AniList."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="mystats")
    async def mystats(self, ctx: commands.Context):
        """Affiche vos statistiques AniList sous forme d'image stylisée."""
        user_id = str(ctx.author.id)
        link = database.get_anilist_link(user_id)
        if not link:
            await ctx.send("❌ Vous n’avez pas encore lié votre compte AniList. Utilisez `!linkanilist`.")
            return

        stats = anilist.get_user_stats(link["anilist_id"])
        if not stats:
            await ctx.send("❌ Impossible de récupérer vos statistiques pour le moment.")
            return

        buf = image.generate_stats_image(ctx.author.name, stats)
        if buf is None:
            await ctx.send("❌ Une erreur est survenue lors de la génération de l’image.")
            return

        await ctx.send(file=discord.File(buf, filename="stats.jpg"))

async def setup(bot: commands.Bot):
    await bot.add_cog(AniListStats(bot))
