import discord
from discord.ext import commands
import os
import asyncio
import logging

# Active les logs pour mieux diagnostiquer
logging.basicConfig(level=logging.INFO)

# Intents nécessaires pour les fonctionnalités
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

# Crée le bot avec le préfixe "!" et les intents
bot = commands.Bot(command_prefix="!", intents=intents)

# Liste des extensions à charger
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
    # Charge chaque extension
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            print(f"✅ Extension chargée : {ext}")
        except Exception as e:
            print(f"❌ Erreur lors du chargement de {ext} : {e}")

    # Récupère le token depuis la variable d’environnement
    token = os.getenv("DISCORD_BOT_TOKEN")
    if token:
        await bot.start(token)
    else:
        print("❌ Le token Discord n’est pas défini. Vérifie la clé : DISCORD_BOT_TOKEN")

if __name__ == "__main__":
    asyncio.run(main())
