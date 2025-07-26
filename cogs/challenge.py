import discord
from discord.ext import commands

class Challenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="anichallenge")
    async def anichallenge(self, ctx):
        await ctx.send("🏆 Défi de la semaine... (placeholder)")

async def setup(bot):
    await bot.add_cog(Challenge(bot))