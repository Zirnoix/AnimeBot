# D'accord. Je vais commencer par le fichier central : bot.py
# Il gère le chargement des extensions (cogs), les intents et la configuration du bot.

import discord
from discord.ext import commands, tasks
import os
import asyncio
import datetime
import time
import json
import requests

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} (ID: {bot.user.id})")
    print("------")
    if not tracker_loop.is_running():
        tracker_loop.start()

async def load_extensions():
    for filename in os.listdir("cogs"):
        if filename.endswith(".py") and not filename.startswith("_") and filename != "challenge.py":
            await bot.load_extension(f"cogs.{filename[:-3]}")

async def main():
    await load_extensions()
    await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())

# ---------------- TRACKER LOOP ----------------
TRACKED_FILE = "tracked_anime.json"
NOTIFIED_FILE = "notified_cache.json"
CONFIG_FILE = "config.json"
ANILIST_API_URL = "https://graphql.anilist.co"

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fetch_airing_info(anime_title):
    query = '''
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        title { romaji }
        nextAiringEpisode {
          airingAt
          episode
        }
      }
    }
    '''
    variables = {"search": anime_title}
    response = requests.post(ANILIST_API_URL, json={"query": query, "variables": variables}, headers={"Content-Type": "application/json"})
    if response.status_code != 200:
        return None
    data = response.json().get("data", {}).get("Media")
    return data if data and data.get("nextAiringEpisode") else None

@tasks.loop(minutes=10)
async def tracker_loop():
    print("[Tracker] Lancement de la vérification des épisodes à venir...")
    tracked = load_json(TRACKED_FILE)
    notified = load_json(NOTIFIED_FILE)
    config = load_json(CONFIG_FILE)
    channel_id = config.get("notification_channel_id")
    channel = bot.get_channel(channel_id) if channel_id else None
    now = int(time.time())

    for user_id, anime_list in tracked.items():
        user = await bot.fetch_user(int(user_id))
        for anime in anime_list:
            info = fetch_airing_info(anime)
            if not info:
                continue

            airing = info["nextAiringEpisode"]
            time_left = airing["airingAt"] - now
            key = f"{user_id}_{anime}_{airing['episode']}"

            if 0 < time_left <= 1800 and key not in notified:
                embed = discord.Embed(title=f"⏰ Bientôt un épisode !", color=0xffc107)
                embed.add_field(name=info["title"]["romaji"], value=f"Épisode **{airing['episode']}** dans moins de **30 minutes**.", inline=False)
                embed.set_footer(text="AnimeBot - Suivi personnalisé")
                try:
                    await user.send(embed=embed)
                    if channel:
                        await channel.send(embed=embed)
                    notified[key] = True
                    print(f"[Tracker] Notification envoyée à {user.name} pour {anime}")
                except:
                    print(f"[Tracker] Échec d'envoi à {user_id}")

    save_json(NOTIFIED_FILE, notified)
