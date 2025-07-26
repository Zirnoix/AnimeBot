from discord.ext import commands
import discord
import random
import json
import aiohttp
from modules.utils import load_json, save_json, get_user_level
from modules.title_cache import get_random_anime_title

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx):
        await ctx.send("🎮 Lancement du quiz... (placeholder)")

    @commands.command(name="quiztop")
    async def quiz_top(self, ctx):
        await ctx.send("🏆 Classement du quiz... (placeholder)")

    @commands.command(name="myrank")
    async def my_rank(self, ctx):
        await ctx.send("📊 Ton rang... (placeholder)")

async def setup(bot):
    await bot.add_cog(Quiz(bot))
