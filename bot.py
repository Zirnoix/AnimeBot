import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    await load_all_cogs()

async def load_all_cogs():
    for folder in ["cogs"]:
        for filename in os.listdir(folder):
            if filename.endswith(".py"):
                try:
                    await bot.load_extension(f"{folder}.{filename[:-3]}")
                    print(f"✅ Cog chargé : {filename}")
                except Exception as e:
                    print(f"❌ Erreur chargement {filename} : {e}")

async def main():
    async with bot:
        await bot.start(os.getenv("DISCORD_BOT_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())