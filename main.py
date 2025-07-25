import discord
from discord.ext import commands
import os
import asyncio
import logging
import traceback  # Pour afficher les erreurs en détail
import helpers.anilist_utils  # Forcer l'import pour que le code dans le fichier s'exécute

print("✅ TEST CONSOLE — Le script main.py démarre bien.")

# Active les logs pour mieux diagnostiquer
logging.basicConfig(level=logging.INFO)

# Intents nécessaires
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

# Création du bot
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Modules à charger
extensions = [
    "modules.commands.quiz",
    "modules.commands.challenge",
    "modules.commands.classement",
    "modules.commands.recherche",
    "modules.commands.stats",
    "modules.commands.utilitaires",
    "modules.commands.notifications",
    "modules.commands.planning",
    "modules.commands.profil",
    "modules.commands.help"
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
            print(f"❌ Erreur lors du chargement de {ext} :")
            traceback.print_exc()

    # Token depuis Render
    token = os.getenv("DISCORD_BOT_TOKEN")
    if token:
        await bot.start(token)
    else:
        print("❌ Le token Discord n’est pas défini. Vérifie la clé DISCORD_BOT_TOKEN sur Render.")

if __name__ == "__main__":
    asyncio.run(main())
