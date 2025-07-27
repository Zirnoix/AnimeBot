from discord.ext import commands
import discord
class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def help(self, ctx):
        await ctx.send('Voici l’aide complète.')
async def setup(bot):
    await bot.add_cog(Help(bot))