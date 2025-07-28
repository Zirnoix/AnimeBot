import discord
from discord.ext import commands
from modules.anilist import get_user_stats, get_duel_stats
from modules.user_settings import get_anilist_username

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="stats")
    async def stats(self, ctx):
        username = get_anilist_username(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu dois lier ton compte Anilist avec `!linkanilist <pseudo>`.")
            return

        stats = get_user_stats(username)
        if not stats:
            await ctx.send("❌ Impossible de récupérer les statistiques.")
            return

        embed = discord.Embed(title=f"📊 Statistiques Anilist de {username}", color=0x7289da)
        embed.add_field(name="Anime vus", value=stats['anime_count'])
        embed.add_field(name="Temps total", value=stats['time_watched'])
        embed.add_field(name="Score moyen", value=stats['mean_score'])
        await ctx.send(embed=embed)

    @commands.command(name="duelstats")
    async def duelstats(self, ctx, pseudo1: str, pseudo2: str):
        stats = get_duel_stats(pseudo1, pseudo2)
        if not stats:
            await ctx.send("❌ Impossible de comparer ces deux utilisateurs.")
            return

        embed = discord.Embed(title=f"⚔️ Duel entre {pseudo1} et {pseudo2}", color=0xe74c3c)
        embed.add_field(name=pseudo1, value=f"{stats['user1']} anime vus")
        embed.add_field(name=pseudo2, value=f"{stats['user2']} anime vus")
        embed.add_field(name="Différence", value=f"{stats['diff']} anime")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
