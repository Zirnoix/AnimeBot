
import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")

async def main():
    try:
        await bot.load_extension("modules.commands.test")
        print("✅ Extension 'test' chargée")
    except Exception as e:
        print(f"❌ Erreur chargement extension : {e}")

    token = os.getenv("DISCORD_TOKEN")
    if token:
        await bot.start(token)
    else:
        print("❌ Le token Discord n’est pas défini.")

if __name__ == "__main__":
    asyncio.run(main())
