# restructured_bot/cogs/stats.py

import discord
from discord.ext import commands
from restructured_bot.modules import core, image

class UserStats(commands.Cog):
    """Statistiques de visionnage d'animes."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mystats")
    async def mystats(self, ctx: commands.Context):
        """Affiche vos statistiques de visionnage AniList sous forme d'image."""
        user_id = str(ctx.author.id)
        username = core.get_user_anilist(user_id)

        if not username:
            await ctx.send("❌ Vous n'avez pas encore lié votre compte AniList avec `!linkanilist`.")
            return

        stats = core.query_user_stats(username)
        if not stats:
            await ctx.send("❌ Impossible de récupérer vos statistiques.")
            return

        buf = image.generate_stats_card(username, stats)
        if buf is None:
            await ctx.send("❌ Erreur lors de la génération de l'image.")
            return

        await ctx.send(file=discord.File(buf, filename="mystats.jpg"))

    @commands.command(name="mychart")
    async def mychart(self, ctx: commands.Context):
        """Affiche un diagramme des genres les plus regardés (AniList)."""
        user_id = str(ctx.author.id)
        username = core.get_user_anilist(user_id)

        if not username:
            await ctx.send("❌ Vous n'avez pas encore lié votre compte AniList avec `!linkanilist`.")
            return

        genre_data = core.get_genre_distribution(username)
        if not genre_data:
            await ctx.send("❌ Aucune donnée trouvée pour ce compte.")
            return

        buf = image.generate_genre_chart(username, genre_data)
        if buf is None:
            await ctx.send("❌ Erreur lors de la génération du graphique.")
            return

        await ctx.send(file=discord.File(buf, filename="mychart.jpg"))


async def setup(bot):
    await bot.add_cog(UserStats(bot))
