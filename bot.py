# bot.py

import discord
from discord.ext import commands
import os
import asyncio
from datetime import datetime, timezone
import logging

# Activer les logs (s'affiche dans Render)
logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.messages = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.launch_time = datetime.now(timezone.utc)

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
    logging.info(f"[✅] Connecté en tant que {bot.user.name}")
    logging.info("[📡] Le bot est prêt à l’action !")

@bot.event
async def on_command_error(ctx, error):
    # Affiche toutes les erreurs dans Discord
    import traceback
    tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    tb_short = tb[:1900]  # Discord limite à 2000 caractères
    await ctx.send(f"```py\n{tb_short}```")

async def main():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            logging.info(f"[📥] Cog chargé : {cog}")
        except Exception as e:
            logging.error(f"[❌] Erreur lors du chargement de {cog} : {e}")

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logging.critical("❌ Token introuvable. As-tu bien configuré 'DISCORD_BOT_TOKEN' dans Render ?")
        return

    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
