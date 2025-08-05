import os, logging, traceback
from datetime import datetime, timezone

import discord
from discord.ext import commands

# Configuration du logger de base (niveau INFO)
logging.basicConfig(level=logging.INFO)

# Enregistrer l'heure de lancement du bot en UTC (objet datetime timezone-aware)
launch_time = datetime.now(timezone.utc)

# Sous-classe Bot personnalisée pour charger dynamiquement les cogs
class MyBot(commands.Bot):
    async def setup_hook(self):
        # Parcourt tous les fichiers .py du dossier cogs et tente de les charger
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('_'):
                extension = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(extension)
                    logging.info(f"Extension {extension} chargée avec succès.")
                except Exception:
                    logging.error(
                        f"Erreur lors du chargement de l'extension {extension} :\n{traceback.format_exc()}"
                    )

# Définir les intents (incluant le contenu des messages)
intents = discord.Intents.default()
intents.message_content = True

# Initialiser le bot avec un préfixe de commande et les intents définis
bot = MyBot(command_prefix="!", intents=intents)

# Événement déclenché lorsque le bot se connecte avec succès
@bot.event
async def on_ready():
    logging.info(f"Connecté en tant que {bot.user} (ID: {bot.user.id})")

# Récupérer le token du bot depuis les variables d'environnement et démarrer le bot
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    logging.error("Le token Discord n'a pas été trouvé. Veuillez le définir dans les variables d'environnement.")
else:
    bot.run(TOKEN)
