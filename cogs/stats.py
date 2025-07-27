# Stats Cog complet iciimport discord
from discord.ext import commands
from modules.anilist import get_user_stats, get_duel_stats

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mystats")
    async def mystats(self, ctx):
        embed = await get_user_stats(ctx.author.id)
        await ctx.send(embed=embed)

    @commands.command(name="duelstats")
    async def duelstats(self, ctx, member: discord.Member):
        embed = await get_duel_stats(ctx.author.id, member.id)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
