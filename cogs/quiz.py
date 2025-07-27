from discord.ext import commands
class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def animequiz(self, ctx):
        await ctx.send('🎮 Lancement du quiz...')
async def setup(bot):
    await bot.add_cog(Quiz(bot))