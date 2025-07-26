import discord
from discord.ext import commands
import random
import json
import os
from modules.utils import load_json, save_json

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="animequiz")
    async def animequiz(self, ctx):
        await ctx.send("🎮 Lancement du quiz... (placeholder)")

async def setup(bot):
    await bot.add_cog(Quiz(bot))