import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

extensions = [
    "modules.commands.quiz",
    "modules.commands.challenge",
    "modules.commands.classement",
    "modules.commands.recherche",
    "modules.commands.stats",
    "modules.commands.utilitaires",
    "modules.commands.notifications",
    "modules.commands.planning",
    "modules.commands.profil"
]

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")

async def main():
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            print(f"✅ Extension chargée : {ext}")
        except Exception as e:
            print(f"❌ Erreur lors du chargement de {ext} : {e}")

    token = os.getenv("DISCORD_TOKEN")
    if token:
        await bot.start(token)
    else:
        print("❌ Le token Discord n’est pas défini (clé DISCORD_TOKEN)")

if __name__ == "__main__":
    asyncio.run(main())