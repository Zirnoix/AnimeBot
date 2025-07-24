import discord
from discord.ext import commands
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Chargement des modules (les extensions)
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
        print(f"✅ {ext} chargé")
    except Exception as e:
        print(f"❌ Erreur en chargeant {ext} : {e}")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# Lancer le bot
bot.run(os.getenv("DISCORD_TOKEN"))
