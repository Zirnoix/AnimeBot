import discord
from discord.ext import commands
from modules.user_settings import link_anilist_account, track_anime, untrack_anime, get_tracked_anime

class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="anitracker")
    async def anitracker(self, ctx):
        embed = await get_tracked_anime(ctx.author.id)
        await ctx.send(embed=embed)

    @commands.command(name="track")
    async def track(self, ctx, *, title: str):
        msg = track_anime(ctx.author.id, title)
        await ctx.send(msg)

    @commands.command(name="untrack")
    async def untrack(self, ctx, *, title: str):
        msg = untrack_anime(ctx.author.id, title)
        await ctx.send(msg)

async def setup(bot):
    await bot.add_cog(Tracker(bot))
# Tracker Cog complet ici
