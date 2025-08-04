# bot.py

import discord
from discord.ext import commands
import os
import asyncio

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

async def load_cogs():
    for folder in ["cogs"]:
        for filename in os.listdir(folder):
            if filename.endswith(".py"):
                try:
                    await bot.load_extension(f"{folder}.{filename[:-3]}")
                    print(f"✅ Loaded {filename}")
                except Exception as e:
                    print(f"❌ Failed to load {filename}: {e}")

@bot.event
async def on_ready():
    print(f"🔧 Bot connecté en tant que {bot.user.name}")
    print("------")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
