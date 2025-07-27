from discord.ext import commands
from modules.anilist import get_challenge_data, get_weekly_challenge, complete_challenge

class Challenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="anichallenge")
    async def anichallenge(self, ctx):
        embed = await get_challenge_data(ctx.author.id)
        await ctx.send(embed=embed)

    @commands.command(name="weekly")
    async def weekly(self, ctx):
        embed = await get_weekly_challenge()
        await ctx.send(embed=embed)

    @commands.command(name="complete")
    async def complete(self, ctx):
        embed = await complete_challenge(ctx.author.id)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Challenge(bot))
