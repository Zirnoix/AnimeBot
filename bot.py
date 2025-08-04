# bot.py

import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import datetime
from datetime import datetime, timezone

# Charger les variables d’environnement (Render gère ça automatiquement)
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.messages = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.launch_time = datetime.now(timezone.utc)

# Liste de tous les cogs à charger (tu peux en rajouter ici)
COGS = [
    "cogs.anilist",
    "cogs.duel",
    "cogs.guess",
    "cogs.planning",
    "cogs.profile",
    "cogs.quiz",
    "cogs.stats",
    "cogs.tracker",
    "cogs.help",
    "cogs.ping"
]

@bot.event
async def on_ready():
    print(f"[✅] Connecté en tant que {bot.user.name}")
    print("[📡] Le bot est prêt à l’action !")

@bot.event
async def on_command_error(ctx, error):
    import traceback
    tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    await ctx.send(f"```py\n{tb[:1900]}```")


async def main():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"[📥] Cog chargé : {cog}")
        except Exception as e:
            print(f"[❌] Erreur lors du chargement de {cog} : {e}")

    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("❌ Le token Discord est introuvable dans les variables d’environnement.")
        return

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
