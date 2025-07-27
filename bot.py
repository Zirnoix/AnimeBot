import discord
from discord.ext import commands
import asyncio
import os

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all(), help_command=None)

async def load():
    extensions = [
        'cogs.quiz', 'cogs.help', 'cogs.challenge', 'cogs.tracker',
        'cogs.episodes', 'cogs.stats', 'cogs.planning'
    ]
    for ext in extensions:
        await bot.load_extension(ext)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

async def main():
    async with bot:
        await load()
        await bot.start(os.getenv("DISCORD_TOKEN"))

asyncio.run(main())
