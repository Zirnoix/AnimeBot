# Episodes Cog complet iciimport discord
from discord.ext import commands
from modules.anilist import get_next_episode_for_user, get_next_airing_episodes

class Episodes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="next")
    async def next_episode(self, ctx):
        embed = await get_next_airing_episodes(limit=5)
        await ctx.send(embed=embed)

    @commands.command(name="monnext")
    async def user_next_episode(self, ctx):
        embed = await get_next_episode_for_user(ctx.author.id)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Episodes(bot))
