from discord.ext import commands

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx):
        await ctx.send("🎮 Quiz lancé ! (commande test)")

async def setup(bot):
    await bot.add_cog(Quiz(bot))