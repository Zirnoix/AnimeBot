import discord
from discord.ext import commands
from modules.anilist import get_personal_planning, get_seasonal_anime

class Planning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="monplanning")
    async def monplanning(self, ctx):
        embed = await get_personal_planning(ctx.author.id)
        await ctx.send(embed=embed)

    @commands.command(name="seasonal")
    async def seasonal(self, ctx):
        embed = await get_seasonal_anime()
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Planning(bot))
