from discord.ext import commands
import discord
from modules.utils import get_user_level
from modules.title_cache import get_random_anime_title

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx):
        title = get_random_anime_title()
        await ctx.send(f"🎮 Devine l'anime : ||{title}||")

    @commands.command(name="quiztop")
    async def quiz_top(self, ctx):
        await ctx.send("🏆 Classement des joueurs (mock).")

    @commands.command(name="myrank")
    async def my_rank(self, ctx):
        level = get_user_level(45)
        await ctx.send(f"📊 Tu es actuellement au niveau : {level}")

async def setup(bot):
    await bot.add_cog(Quiz(bot))
