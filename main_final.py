import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Charger les variables d'environnement si .env présent
load_dotenv()

# Intents recommandés pour bots avec interactions
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Liste des extensions (modules de commande)
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

for ext in extensions:
    try:
        bot.load_extension(ext)
        print(f"✅ Module chargé : {ext}")
    except Exception as e:
        print(f"❌ Erreur lors du chargement de {ext} : {e}")

@bot.event
async def on_ready():
    print(f"🤖 Bot connecté en tant que {bot.user.name} (ID: {bot.user.id})")

# Lancement
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ Le token Discord n’est pas défini dans .env (clé DISCORD_TOKEN)")