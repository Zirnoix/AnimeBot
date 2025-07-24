# AnimeBot — Version finale avec !setchannel, préférences, alertes, !prochains stylisé
import discord
from discord.ext import commands, tasks
import requests
import json
import locale
import random
import asyncio
import os
import pytz
import re
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import unicodedata
import matplotlib.pyplot as plt
from modules.title_cache import load_title_cache, normalize
from modules.title_cache import update_title_cache, load_title_cache
from calendar import monthrange
from babel.dates import format_datetime
from modules.utils import load_json, save_json

# Date actuelle
now = datetime.now()

# Formatage en français
formatted_date = format_datetime(now, "EEEE d MMMM y 'à' HH:mm", locale='fr_FR')

print(formatted_date)


PREFERENCES_FILE = "/data/preferences.json"
QUIZ_SCORES_FILE = "/data/quiz_scores.json"
LINKED_FILE = "/data/linked_users.json"
LEVELS_FILE = "/data/quiz_levels.json"
TRACKER_FILE = "/data/anitracker.json"
CHALLENGES_FILE = "/data/challenges.json"
WEEKLY_FILE = "/data/weekly.json"
USER_SETTINGS_FILE = "/data/user_settings.json"
NOTIFIED_FILE = "/data/notified.json"
LINKS_FILE = "/data/user_links.json"

TITLE_CACHE_FILE = "/data/title_cache.json"

WINNER_FILE = "/data/quiz_winner.json"

def load_quiz_winner():
    if not os.path.exists(WINNER_FILE):
        return {}
    with open(WINNER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_quiz_winner(data):
    with open(WINNER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_title_cache():
    if os.path.exists(TITLE_CACHE_FILE):
        with open(TITLE_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

title_cache = load_title_cache()

for path in [
    PREFERENCES_FILE, QUIZ_SCORES_FILE, TRACKER_FILE, WEEKLY_FILE,
    LINKED_FILE, LEVELS_FILE, CHALLENGES_FILE,
    USER_SETTINGS_FILE, NOTIFIED_FILE, LINKS_FILE
]:
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)

for path in [
    PREFERENCES_FILE, QUIZ_SCORES_FILE, "/data/.json", "/data/weekly.json",
    "/data/linked_users.json", "/data/quiz_levels.json", "/data/challenges.json",
    USER_SETTINGS_FILE, NOTIFIED_FILE, LINKS_FILE
]:
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)

def title_variants(title_data):
    titles = set()

    for key in ['romaji', 'english', 'native']:
        t = title_data.get(key)
        if not t:
            continue
        base = normalize(t)
        titles.add(base)
        titles.add(re.sub(r"(s\d|season|part|final|ver\d+|[^a-zA-Z\s])", "", base))
        for word in base.split():
            if len(word) >= 4:
                titles.add(word)

    # Ajout depuis le cache
    cache = load_title_cache()
    for entry in cache.values():
        for t in entry["titles"]:
            titles.add(t)

    return set(titles)
    
def normalize(text):
    import unicodedata
    if not text:
        return ""
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')  # supprime les accents
    return ''.join(e for e in text.lower() if e.isalnum() or e.isspace()).strip()

def update_title_cache():
    print("[CACHE] Mise à jour des titres AniList...")

    query = '''
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME, status_in: [CURRENT, COMPLETED, PAUSED, DROPPED, PLANNING]) {
        lists {
          entries {
            media {
              title { romaji english native }
            }
          }
        }
      }
    }
    '''
    variables = {"name": ANILIST_USERNAME}

    try:
        result = query_anilist(query, variables)
        if not result or "data" not in result:
            raise ValueError("Données manquantes ou incorrectes dans la réponse AniList.")

        entries = result["data"]["MediaListCollection"]["lists"]
        all_titles = []

        for lst in entries:
            for entry in lst["entries"]:
                titles = entry["media"]["title"]
                all_titles.append(titles)

        cache = {}
        for t in all_titles:
            variants = title_variants(t)
            for v in variants:
                cache[v] = t["romaji"]

        save_json("title_cache.json", cache)
        print(f"[CACHE ✅] {len(cache)} titres ajoutés au cache.")

    except Exception as e:
        print(f"[CACHE ❌] Erreur lors de la mise à jour : {e}")
        
def title_variants(title_data):
    titles = set()

    # 1. Titres de base (romaji, english, native)
    for key in ['romaji', 'english', 'native']:
        t = title_data.get(key)
        if not t:
            continue
        base = normalize(t)
        clean = re.sub(r"(saison|season|s\d|2nd|second|3rd|third|final|part \d+|ver\d+|[^\w\s])", "", base, flags=re.IGNORECASE).strip()
        titles.add(base)
        titles.add(clean)
        for word in clean.split():
            if len(word) >= 4:
                titles.add(word)

    # 2. Titres issus du cache (automatique)
    cache = load_title_cache()
    for entry in cache.values():
        variants = entry["titles"]
        titles.update(variants)

    # 3. Synonymes manuels (ceux que tu as déjà ajoutés à la main)
    aliases = {
        "one piece": {"op", "onepiece", "op film", "one piece stampede", "stampede"},
        "hajime no ippo": {"ippo", "hni", "champion road", "hajime"},
        "attack on titan": {"snk", "aot", "shingeki", "shingeki no kyojin"},
        "my hero academia": {"mha", "boku no hero academia", "hero academia"},
        "sword art online": {"sao"},
        "demon slayer": {"kimetsu no yaiba", "kny", "demon slayer kimetsu"},
        "jujutsu kaisen": {"jjk"},
        "hunter x hunter": {"hxh"},
        "tokyo ghoul": {"tg"},
        "nier automata": {"nier"},
        "bleach": {"bleach", "tybw"},
        "mob psycho 100": {"mob", "mob psycho"},
        "one punch man": {"opm"},
        "naruto": {"naruto", "shippuden"},
        "black clover": {"blackclover"},
        "dr stone": {"dr. stone"},
        "re zero": {"rezero", "re:zero"},
        "tokyo revengers": {"revengers", "tokrev"},
        "chainsaw man": {"chainsawman", "csm"},
        "fire force": {"fire force", "enka"},
        "fairy tail": {"fairytail", "ft"},
        "blue lock": {"bluelock", "bl"},
        "spy x family": {"spyxfamily", "spy family", "sxF"},
        "classroom of the elite": {"cote", "classroom"},
        "the rising of the shield hero": {"tate", "shield hero"},
        "made in abyss": {"mia", "abyss"},
        "the promised neverland": {"tpn", "yakusoku"},
        "oshi no ko": {"oshinoko", "onk"},
        "hell’s paradise": {"jigokuraku"},
        "vinland saga": {"vinland"},
        "bocchi the rock": {"bocchi"},
        "solo leveling": {"sololeveling", "sl"},
        "mashle": {"mashle"},
        "frieren": {"sousou no frieren", "frieren"},
        "steins gate": {"steins", "sg"},
        "meitantei conan": {"detective conan", "conan"},
        "no game no life": {"ngnl"},
        "future diary": {"mirai nikki"},
        "parasyte": {"kiseijuu"},
        "rent a girlfriend": {"kanokari"},
        "your name": {"kimi no na wa", "yourname"},
        "a silent voice": {"koe no katachi", "silent voice"},
        "charlotte": {"charlotte"},
        "toradora": {"toradora"},
        "angel beats": {"angelbeats"},
        "clannad": {"clannad"},
        "violet evergarden": {"violet"},
        "code geass": {"cg"},
        "death note": {"deathnote"},
        "erased": {"boku dake ga inai machi"},
        "akame ga kill": {"akame"},
        "zom 100": {"zom100", "bucket list"},
        "86": {"eighty six"},
        "mushoku tensei": {"jobless reincarnation", "mushoku"},
        "kaguya sama": {"love is war", "kaguya"},
        "noragami": {"yato"},
        "five toubun": {"quintuplets", "5toubun"},
        "reincarnated as a slime": {"tensura"},
        "fullmetal alchemist": {"fma", "brotherhood"},
        "danganronpa": {"dr"},
        "k-on": {"kon"},
        "your lie in april": {"shigatsu"},
        "bunny girl senpai": {"rascal", "bunny girl"},
        "horimiya": {"horimiya"},
        "another": {"another"},
        "angel beats": {"angel beats"},
        "gintama": {"gintoki"},
        "overlord": {"overlord"},
        "eromanga sensei": {"eromanga"},
        "highschool dxd": {"dxd"},
        "tokyo avengers": {"tokrev"},
        "konosuba": {"konosuba"},
        "naruto shippuden": {"naruto", "shippuden"}
    }

    base_all = [normalize(title_data.get(k, "")) for k in ['romaji', 'english', 'native']]
    for b in base_all:
        for key, values in aliases.items():
            if key in b:
                titles.update(values)

    return set(normalize(t) for t in titles if len(t) > 1)


# 📁 Chargement des préférences utilisateur
PREFERENCES_FILE = "/data/preferences.json"

QUIZ_SCORES_FILE = "/data/quiz_scores.json"

def get_user_anilist(user_id):
    data = load_links()
    return data.get(str(user_id))

def load_tracker():
    try:
        with open("/data/.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_tracker(data):
    with open("/data/.json", "w") as f:
        json.dump(data, f, indent=2)

def get_xp_bar(xp, total, length=10):
    filled = int((xp / total) * length)
    empty = length - filled
    return "▰" * filled + "▱" * empty

def load_weekly():
    try:
        with open("/data/weekly.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_weekly(data):
    with open("/data/weekly.json", "w") as f:
        json.dump(data, f, indent=2)

def load_scores():
    if not os.path.exists(QUIZ_SCORES_FILE):
        return {}
    with open(QUIZ_SCORES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_scores(scores):
    with open(QUIZ_SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2, ensure_ascii=False)

def load_links():
    try:
        with open("/data/linked_users.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_links(data):
    with open("/data/linked_users.json", "w") as f:
        json.dump(data, f, indent=2)

def query_anilist(query: str, variables: dict = None):
    try:
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables or {}},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()
    except:
        return None

def load_levels():
    try:
        with open("/data/quiz_levels.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_levels(data):
    with open("/data/quiz_levels.json", "w") as f:
        json.dump(data, f, indent=2)

def add_xp(user_id, amount=10):
    user_id = str(user_id)
    data = load_levels()
    if user_id not in data:
        data[user_id] = {"xp": 0, "level": 0}

    data[user_id]["xp"] += amount
    level = data[user_id]["level"]
    xp_needed = (level + 1) * 100
    leveled_up = False

    while data[user_id]["xp"] >= xp_needed:
        data[user_id]["xp"] -= xp_needed
        data[user_id]["level"] += 1
        leveled_up = True
        xp_needed = (data[user_id]["level"] + 1) * 100

    save_levels(data)
    return leveled_up, data[user_id]["level"]

def load_challenges():
    try:
        with open("/data/challenges.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_challenges(data):
    with open("/data/challenges.json", "w") as f:
        json.dump(data, f, indent=2)

preferences = load_json(PREFERENCES_FILE)
def save_preferences():
    save_json(PREFERENCES_FILE, preferences)

ImageFont.truetype("fonts/DejaVuSans.ttf", 18)
ImageFont.truetype("fonts/DejaVuSans-Bold.ttf", 24)

start_time = datetime.now(timezone.utc)


# Configuration initiale
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ANILIST_USERNAME = "Zirnoixdcoco"
TIMEZONE = pytz.timezone("Europe/Paris")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Fichiers JSON
CONFIG_FILE = "config.json"
USER_SETTINGS_FILE = "/data/user_settings.json"
NOTIFIED_FILE = "/data/notified.json"

LINKS_FILE = "/data/user_links.json"

# Charger les liens existants
if os.path.exists(LINKS_FILE):
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        user_links = json.load(f)
        # Convert keys to integers (json keys are always strings)
        user_links = {int(k): v for k, v in user_links.items()}
else:
    user_links = {}

def save_user_links():
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_links, f, ensure_ascii=False, indent=2)

OWNER_ID = 180389173985804288

def load_json(file, default):
    if not os.path.exists(file):
        return default
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

def get_config():
    return load_json(CONFIG_FILE, {})

def save_config(data):
    save_json(CONFIG_FILE, data)

user_settings = load_json(USER_SETTINGS_FILE, {})
notified = set(load_json(NOTIFIED_FILE, []))

jours_fr = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi", "Thursday": "Jeudi",
    "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"
}

def genre_emoji(genres):
    emojis = {
        "Action": "⚔️", "Comedy": "😂", "Drama": "🎭", "Fantasy": "🧙‍♂️", "Romance": "💕",
        "Sci-Fi": "🚀", "Horror": "👻", "Mystery": "🕵️", "Sports": "🏅", "Music": "🎵",
        "Slice of Life": "🍃"
    }
    for g in genres:
        if g in emojis: return emojis[g]
    return "🎬"

def build_embed(ep, dt):
    emoji = genre_emoji(ep["genres"])
    embed = discord.Embed(
        title=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
        description=f"📅 {jours_fr[dt.strftime('%A')]} {dt.strftime('%d/%m')} à {dt.strftime('%H:%M')}",
        color=discord.Color.blurple()
    )
    embed.set_thumbnail(url=ep["image"])
    return embed

def get_upcoming_episodes(username):
    import requests
    import json

    query = '''
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME) {
        lists {
          entries {
            media {
              id
              title { romaji }
              coverImage { extraLarge } 
              nextAiringEpisode { airingAt episode }
              genres
            }
          }
        }
      }
    }
    '''

    variables = {"name": username}
    url = "https://graphql.anilist.co"

    try:
        response = requests.post(url, json={"query": query, "variables": variables})
        response.raise_for_status()
        data = response.json()

        entries = []
        for lst in data["data"]["MediaListCollection"]["lists"]:
            for entry in lst["entries"]:
                media = entry.get("media")
                if not media:
                    continue

                next_ep = media.get("nextAiringEpisode")
                if not next_ep or not next_ep.get("airingAt") or not next_ep.get("episode"):
                    continue

                entries.append({
                    "id": media.get("id"),
                    "title": media.get("title", {}).get("romaji", "Inconnu"),
                    "episode": next_ep["episode"],
                    "airingAt": next_ep["airingAt"],
                    "genres": media.get("genres", []),
                    "image": media.get("coverImage", {}).get("extraLarge") 
                })

        print(f"🎯 {len(entries)} épisodes trouvés pour {username}", flush=True)
        return entries

    except Exception as e:
        print(f"[Erreur AniList] {e}", flush=True)
        return []



# Commande !prochains en un seul embed
@bot.command(name="prochains")
async def prochains(ctx, *args):
    filter_genre = None
    limit = 10

    # Traitement des arguments : genre + nombre ou "all"
    for arg in args:
        if arg.isdigit():
            limit = min(100, int(arg))
        elif arg.lower() in ["all", "tout"]:
            limit = 100
        else:
            filter_genre = arg.capitalize()

    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    if not episodes:
        await ctx.send("Aucun épisode à venir.")
        return

    # Filtrer par genre si applicable
    if filter_genre:
        episodes = [ep for ep in episodes if filter_genre in ep.get("genres", [])]

    if not episodes:
        await ctx.send(f"Aucun épisode trouvé pour le genre **{filter_genre}**.")
        return

    episodes = sorted(episodes, key=lambda e: e["airingAt"])[:limit]
    pages = []
    group_size = 5

    for i in range(0, len(episodes), group_size):
        group = episodes[i:i+group_size]
        embed = discord.Embed(
            title=f"📅 Prochains épisodes — Page {len(pages)+1}",
            description=f"Voici les épisodes à venir{f' pour le genre **{filter_genre}**' if filter_genre else ''} :",
            color=discord.Color.blurple()
        )
        for ep in group:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE)
            emoji = genre_emoji(ep["genres"])
        
        # ✅ Variables à calculer avant add_field
            date_fr = format_datetime(dt, "d MMMM", locale='fr_FR')
            jour = jours_fr[dt.strftime('%A')]
            heure = dt.strftime('%H:%M')
            value = f"🗓️ {jour} {date_fr} à {heure}"

            embed.add_field(
                name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                value=value,
                inline=False
            )

        pages.append(embed)


    class Paginator(discord.ui.View):
        def __init__(self): super().__init__(timeout=120); self.index = 0
        @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
        async def prev(self, i, b):
            self.index = max(0, self.index - 1)
            pages[self.index].title = f"📅 Prochains épisodes — Page {self.index+1}/{len(pages)}"
            await i.response.edit_message(embed=pages[self.index], view=self)

        @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
        async def next(self, i, b):
            self.index = min(len(pages)-1, self.index + 1)
            pages[self.index].title = f"📅 Prochains épisodes — Page {self.index+1}/{len(pages)}"
            await i.response.edit_message(embed=pages[self.index], view=self)

        @discord.ui.button(label="❌ Fermer", style=discord.ButtonStyle.danger)
        async def close(self, i, b):
            await i.message.delete()

    if not pages:
        await ctx.send("Aucun épisode à afficher.")
    else:
        pages[0].title = f"📅 Prochains épisodes — Page 1/{len(pages)}"
        await ctx.send(embed=pages[0], view=Paginator())

@bot.command(name="weekly")
async def weekly(ctx, sub=None):
    user_id = str(ctx.author.id)
    data = load_weekly()
    if sub == "complete":
        last = data.get(user_id, {}).get("last_completed")
        if last:
            from datetime import datetime, timedelta
            last_time = datetime.fromisoformat(last)
            if datetime.now() - last_time < timedelta(days=7):
                next_time = last_time + timedelta(days=7)
                wait_days = (next_time - datetime.now()).days + 1
                await ctx.send(f"⏳ Tu as déjà validé ton défi cette semaine.\nTu pourras le refaire dans **{wait_days} jour(s)**.")
                return

        if user_id not in data or not data[user_id].get("active"):
            await ctx.send("❌ Tu n’as pas de défi en cours.")
            return

        challenge = data[user_id]["active"]
        history = data[user_id].get("history", [])
        history.append({"description": challenge["description"], "completed": True})
        data[user_id]["history"] = history
        data[user_id]["active"] = None
        data[user_id]["last_completed"] = datetime.now().isoformat()  # ✅ ligne à ajouter
        save_weekly(data)
        add_xp(ctx.author.id, amount=25)
        await ctx.send(f"✅ Défi terminé : **{challenge['description']}** ! Bien joué 🎉")
        return

    # Liste d’objectifs possibles
    challenges = [
        "Regarder 3 animes du genre Action",
        "Finir un anime de +20 épisodes",
        "Donner une note de 10 à un anime",
        "Regarder un anime en cours de diffusion",
        "Terminer une saison complète en une semaine",
        "Découvrir un anime noté < 70 sur AniList",
        "Regarder un anime de ton genre préféré",
        "Essayer un anime d’un genre que tu n’aimes pas",
        "Faire un duel avec un ami avec `!animebattle`",
        "Compléter un challenge `!anichallenge`"
    ]

    chosen = random.choice(challenges)
    data[user_id] = {
        "active": {"description": chosen},
        "history": data.get(user_id, {}).get("history", [])
    }
    save_weekly(data)
    await ctx.send(f"📅 Ton défi de la semaine :\n**{chosen}**\nQuand tu as terminé, tape `!weekly complete`.")

@bot.command(name="linkanilist")
async def linkanilist(ctx, pseudo: str):
    data = load_links()
    user_id = str(ctx.author.id)
    data[user_id] = pseudo
    save_links(data)
    await ctx.send(f"✅ Ton compte AniList **{pseudo}** a été lié à ton profil Discord.")

@bot.command(name="anichallenge")
async def anichallenge(ctx):
    import random
    import requests

    # Vérifie si un challenge est déjà en cours
    data = load_challenges()
    user_id = str(ctx.author.id)
    if user_id in data and data[user_id].get("active"):
        await ctx.send(f"📌 Tu as déjà un défi en cours : **{data[user_id]['active']['title']}**.\nUtilise `!challenge complete <note/10>` quand tu l’as terminé.")
        return

    # Requête AniList
    for _ in range(10):
        page = random.randint(1, 500)
        query = f'''
        query {{
          Page(perPage: 1, page: {page}) {{
            media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {{
              id
              title {{ romaji }}
              siteUrl
            }}
          }}
        }}
        '''
        url = "https://graphql.anilist.co"
        try:
            res = requests.post(url, json={"query": query})
            anime = res.json()["data"]["Page"]["media"][0]
            title = anime["title"]["romaji"]
            site = anime["siteUrl"]
            data[user_id] = {
                "active": {"id": anime["id"], "title": title},
                "history": data.get(user_id, {}).get("history", [])
            }
            save_challenges(data)
            await ctx.send(f"🎯 Nouveau défi pour **{ctx.author.display_name}** :\n**{title}**\n🔗 {site}\n\nUne fois vu, fais `!challenge complete <note>`")
            return
        except:
            continue

    await ctx.send("❌ Impossible de récupérer un anime pour le challenge.")

@bot.command(name="debugnext")
async def debug_next(ctx):
    episodes = get_upcoming_episodes(ANILIST_USERNAME)

    count = len(episodes)
    if count == 0:
        await ctx.send("❌ Aucun épisode détecté.")
    else:
        await ctx.send(f"🎯 {count} épisodes trouvés pour **{ANILIST_USERNAME}**.")

    for ep in episodes[:5]:  # Limite à 5 pour éviter le spam
        titre = ep["title"]
        num = ep["episode"]
        date = datetime.fromtimestamp(ep["airingAt"], tz=TIMEZONE).strftime("%A %d %B à %H:%M")
        await ctx.send(f"📺 {titre} — Épisode {num} \n🕒 Sortie : {date}")

@bot.command(name="anitracker")
async def anitracker(ctx, sub=None, *, title=None):
    user_id = str(ctx.author.id)
    data = load_tracker()

    if sub == "list":
        series = data.get(user_id, [])
        if not series:
            await ctx.send("📭 Tu ne suis aucun anime.")
        else:
            await ctx.send(f"📺 Animes suivis ({len(series)}):\n" + "\n".join(f"• {s}" for s in series))
        return

    if sub == "remove":
        if not title:
            await ctx.send("❌ Utilise : `!anitracker remove <titre>`")
            return
        series = data.get(user_id, [])
        if title in series:
            series.remove(title)
            data[user_id] = series
            save_tracker(data)
            await ctx.send(f"🗑️ Tu ne suis plus **{title}**.")
        else:
            await ctx.send(f"❌ Tu ne suivais pas **{title}**.")
        return

    # Ajout d’un nouvel anime
    if not title:
        await ctx.send("❌ Utilise : `!anitracker <titre>` pour suivre un anime.")
        return

    series = data.get(user_id, [])
    if title in series:
        await ctx.send(f"📌 Tu suis déjà **{title}**.")
        return

    series.append(title)
    data[user_id] = series
    save_tracker(data)
    await ctx.send(f"✅ Tu suivras **{title}**. Tu recevras un DM à chaque sortie d’épisode.")

@bot.command(name="challenge")
async def challenge_complete(ctx, subcommand=None, note: int = None):
    if subcommand != "complete" or note is None:
        await ctx.send("❌ Utilise : `!challenge complete <note sur 10>`")
        return

    data = load_challenges()
    user_id = str(ctx.author.id)
    if user_id not in data or "active" not in data[user_id]:
        await ctx.send("❌ Tu n’as aucun défi en cours.")
        return

    active = data[user_id]["active"]
    history = data[user_id]["history"]
    history.append({
        "title": active["title"],
        "completed": True,
        "score": note
    })

    data[user_id]["history"] = history
    data[user_id]["active"] = None
    save_challenges(data)
    add_xp(ctx.author.id, amount=15)
    await ctx.send(f"✅ Bien joué **{ctx.author.display_name}** ! Tu as terminé **{active['title']}** avec la note **{note}/10** 🎉")

@bot.command(name="duelstats")
async def duelstats(ctx, opponent: discord.Member = None):
    if opponent is None:
        await ctx.send("❌ Utilise : `!duelstats @ami` pour comparer tes stats avec quelqu’un.")
        return

    data = load_links()
    uid1 = str(ctx.author.id)
    uid2 = str(opponent.id)

    if uid1 not in data or uid2 not in data:
        await ctx.send("❗ Les deux joueurs doivent avoir lié leur compte avec `!linkanilist`.")
        return

    # Récupération des deux pseudos Anilist
    user1, user2 = data[uid1], data[uid2]

    query = '''
    query ($name: String) {
      User(name: $name) {
        statistics {
          anime {
            count
            minutesWatched
            meanScore
            genres { genre count }
          }
        }
      }
    }
    '''

    try:
        stats = {}
        for u in [user1, user2]:
            res = requests.post("https://graphql.anilist.co", json={"query": query, "variables": {"name": u}})
            a = res.json()["data"]["User"]["statistics"]["anime"]
            fav = sorted(a["genres"], key=lambda g: g["count"], reverse=True)[0]["genre"] if a["genres"] else "N/A"
            stats[u] = {
                "count": a["count"],
                "score": round(a["meanScore"], 1),
                "days": round(a["minutesWatched"] / 1440, 1),
                "genre": fav
            }

    except:
        await ctx.send("❌ Impossible de récupérer les statistiques Anilist.")
        return

    # Récupération
    s1, s2 = stats[user1], stats[user2]

    def who_wins(a, b): return "🟰 Égalité" if a == b else "🔼" if a > b else "🔽"

    embed = discord.Embed(
        title=f"📊 Duel de stats : {ctx.author.display_name} vs {opponent.display_name}",
        color=discord.Color.blurple()
    )

    embed.add_field(name="🎬 Animés vus", value=f"{s1['count']} vs {s2['count']} {who_wins(s1['count'], s2['count'])}", inline=False)
    embed.add_field(name="⭐ Score moyen", value=f"{s1['score']} vs {s2['score']} {who_wins(s1['score'], s2['score'])}", inline=False)


@bot.command(name="quiztop")
async def quiztop(ctx):
    import calendar

    scores = load_scores()
    if not scores:
        await ctx.send("🏆 Aucun score enregistré pour l’instant.")
        return

    leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_title(score):
        levels = [
            (100, "👑 Dieu de l'Anime"),
            (95, "💫 Génie légendaire"),
            (90, "🔥 Maître incontesté"),
            (85, "🌟 Pro absolu"),
            (80, "🎯 Otaku ultime"),
            (75, "🎬 Cinéphile expert"),
            (70, "🧠 Stratège anime"),
            (65, "⚡ Analyste senior"),
            (60, "📺 Passionné confirmé"),
            (55, "🎮 Joueur fidèle"),
            (50, "📘 Fan régulier"),
            (45, "💡 Connaisseur"),
            (40, "📀 Binge-watcher"),
            (35, "🎵 Amateur éclairé"),
            (30, "🎙️ Apprenti curieux"),
            (25, "📚 Étudiant otaku"),
            (20, "📦 Débutant prometteur"),
            (15, "🌱 Petit curieux"),
            (10, "🍼 Nouveau joueur"),
            (5,  "🔰 Padawan"),
            (0,  "🐣 Nouvel arrivant")
        ]
        for threshold, title in levels:
            if score >= threshold:
                return title
        return "❓ Inconnu"

    desc = ""
    for i, (uid, score) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(int(uid))
            title = get_title(score)
            desc += f"{i}. **{user.display_name}** — {score} pts {title}\n"
        except:
            continue

    embed = discord.Embed(
        title="🏆 Classement Anime Quiz",
        description=desc,
        color=discord.Color.gold()
    )

    # ⏳ Affiche le temps restant avant reset mensuel
    now = datetime.now(tz=TIMEZONE)
    _, last_day = calendar.monthrange(now.year, now.month)
    reset_date = datetime(now.year, now.month, last_day, 23, 59, tzinfo=TIMEZONE)
    remaining = reset_date - now
    days_left = remaining.days + 1
    embed.set_footer(text=f"⏳ Réinitialisation dans {days_left} jour(s)")

    # 🥇 Vainqueur du mois précédent
    winner_data = load_json("last_quiz_winner.json", {"username": "Inconnu", "score": 0})
    if winner_data and "uid" in winner_data:
        try:
            prev_user = await bot.fetch_user(int(winner_data["uid"]))
            embed.add_field(
                name="🥇 Vainqueur du mois dernier",
                value=f"**{prev_user.display_name}**",
                inline=False
            )
        except:
            pass

    await ctx.send(embed=embed)


@bot.command(name="animebattle")
async def anime_battle(ctx, adversaire: discord.Member = None):
    if adversaire is None:
        await ctx.send("❌ Tu dois mentionner un adversaire : `!animebattle @pseudo`")
        return

    if adversaire.bot:
        await ctx.send("🤖 Tu ne peux pas défier un bot.")
        return

    if adversaire == ctx.author:
        await ctx.send("🙃 Tu ne peux pas te défier toi-même.")
        return

    await ctx.send(f"🎮 Duel entre **{ctx.author.display_name}** et **{adversaire.display_name}** lancé !")

    joueurs = [ctx.author, adversaire]
    scores = {p.id: 0 for p in joueurs}

    for numero in range(1, 4):
        await ctx.send(f"❓ Question {numero}/3...")

        anime = None
        for _ in range(10):
            page = random.randint(1, 500)
            query = f'''
            query {{
              Page(perPage: 1, page: {page}) {{
                media(type: ANIME, isAdult: false, sort: SCORE_DESC) {{
                  id
                  title {{ romaji english native }}
                  description(asHtml: false)
                }}
              }}
            }}
            '''
            data = query_anilist(query)
            try:
                anime = data["data"]["Page"]["media"][0]
                break
            except:
                continue

        if not anime:
            await ctx.send("❌ Impossible de récupérer un anime.")
            return

        # Traduction de la description
        raw_desc = anime.get("description", "Pas de description.").split(".")[0] + "."
        try:
            from deep_translator import GoogleTranslator
            desc = GoogleTranslator(source='auto', target='fr').translate(raw_desc)
        except:
            desc = raw_desc

        embed = discord.Embed(
            title="🧠 Devine l’anime",
            description=f"**Description :**\n{desc}\n\n*15 secondes pour répondre !*",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

        correct_titles = set()

        anime_id = str(anime.get("id"))
        if anime_id in title_cache:
            correct_titles = set(title_cache[anime_id])
        else:
            correct_titles = title_variants(anime["title"])  # fallback au cas où


        def check(m):
            return m.author in joueurs and normalize(m.content) in bonnes_reponses

        try:
            msg = await bot.wait_for("message", timeout=15.0, check=check)
            scores[msg.author.id] += 1
            await ctx.send(f"✅ Bonne réponse de **{msg.author.display_name}** !")
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé. La bonne réponse était **{anime['title']['romaji']}**.")

    j1, j2 = joueurs
    s1, s2 = scores[j1.id], scores[j2.id]
    if s1 == s2:
        resultat = f"🤝 Égalité parfaite entre **{j1.display_name}** et **{j2.display_name}** ! ({s1} - {s2})"
    else:
        gagnant = j1 if s1 > s2 else j2
        add_xp(gagnant.id, amount=20)
        resultat = f"🏆 Victoire de **{gagnant.display_name}** ! Score final : {s1} - {s2}"

    now = datetime.now()
    days_left = monthrange(now.year, now.month)[1] - now.day
    embed.set_footer(text=f"🏁 Réinitialisation dans {days_left} jour(s) — AnimeBot")

    await ctx.send(resultat)

@bot.command(name="myrank")
async def myrank(ctx):
    levels = load_levels()
    lvl = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
    xp = lvl["xp"]
    level = lvl["level"]
    next_xp = (level + 1) * 100
    bar = get_xp_bar(xp, next_xp)

    embed = discord.Embed(
        title=f"🏅 Rang de {ctx.author.display_name}",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="🎮 Niveau & XP",
        value=f"Lv. {level} – {xp}/{next_xp} XP\n`{bar}`\nTitre : **{get_title(level)}**",
        inline=False
    )

    await ctx.send(embed=embed)

# Système de titres fun
def get_title(level):
    titles = [
        (0, "🌱 Débutant"),
        (2, "📘 Curieux"),
        (4, "🎧 Binge-watcheur"),
        (6, "🥢 Ramen addict"),
        (8, "🧑‍🎓 Apprenti Weeb"),
        (10, "🎮 Fan de Shonen"),
        (12, "🎭 Explorateur de genres"),
        (14, "📺 Watcher de l'extrême"),
        (16, "🧠 Analyste amateur"),
        (18, "🔥 Otaku confirmé"),
        (20, "🪩 Esprit de convention"),
        (22, "🧳 Voyageur du multigenre"),
        (24, "🎙️ Dubbé en VOSTFR"),
        (26, "📚 Encyclopedia animée"),
        (28, "💥 Protagoniste secondaire"),
        (30, "🎬 Critique d'élite"),
        (32, "🗾 Stratège de planning"),
        (34, "🐉 Dompteur de shonen"),
        (36, "🧬 Théoricien d'univers"),
        (38, "🧳 Itinérant du sakuga"),
        (40, "🌠 Otaku ascendant"),
        (43, "🎯 Tacticien de la hype"),
        (46, "🛡️ Défenseur du bon goût"),
        (50, "👑 Maître du classement MAL"),
        (52, "🧩 Gardien du lore oublié"),
        (55, "🌀 Téléporté dans un isekai"),
        (58, "💫 Architecte de saison"),
        (60, "📀 Possesseur de l’ultime DVD"),
        (63, "🥷 Fan d’openings introuvables"),
        (66, "🧛 Mi-humain, mi-anime"),
        (70, "🎴 Détenteur de cartes rares"),
        (74, "🪐 Légende du slice of life"),
        (78, "🧝 Mage du genre romance"),
        (82, "☄️ Héros du binge infini"),
        (86, "🗡️ Gardien du storytelling"),
        (90, "🔱 Titan de la narration"),
        (91, "🔮 Prophète de la japanimation"),
        (93, "🧙 Sage des opening 2000+"),
        (95, "🕊️ Émissaire de Kyoto Animation"),
        (97, "🕶️ Stratège d'univers partagés"),
        (99, "👼 Incarnation de la passion"),
        (100, "🧠 Le Grand Archiviste Suprême 🏆")
    ]

    result = "🌱 Débutant"
    for lvl, name in titles:
        if level >= lvl:
            result = name
        else:
            break
    return result

    scores = load_scores()
    user_id = str(ctx.author.id)


    def get_title(score):
        if score >= 15:
            return "🧠 Légende"
        elif score >= 10:
            return "🔥 Otaku"
        elif score >= 6:
            return "💡 Connaisseur"
        elif score >= 3:
            return "📺 Amateur"
        else:
            return "🌱 Débutant"

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    rank = next((i + 1 for i, (uid, _) in enumerate(sorted_scores) if uid == user_id), None)
    score = scores[user_id]
    title = get_title(score)

    embed = discord.Embed(
        title=f"🎖️ Ton rang dans l'Anime Quiz",
        description=(
            f"**👤 Pseudo :** {ctx.author.display_name}\n"
            f"**🏅 Rang :** #{rank} sur {len(sorted_scores)} joueurs\n"
            f"**🔢 Score :** {score} points\n"
            f"**🎯 Titre :** {title}"
        ),
        color=discord.Color.orange()
    )


@bot.command(name="todayinhistory")
async def todayinhistory(ctx):
    day = datetime.now().day
    month = datetime.now().month

    query = f'''
    query {{
      Page(perPage: 1, sort: START_DATE_DESC) {{
        media(type: ANIME, startDate_like: "%-{month:02d}-{day:02d}") {{
          title {{ romaji }}
          startDate {{ year }}
          siteUrl
        }}
      }}
    }}
    '''
    data = query_anilist(query)
    if not data or not data["data"]["Page"]["media"]:
        await ctx.send("❌ Aucun événement marquant trouvé pour aujourd’hui.")
        return

    anime = data["data"]["Page"]["media"][0]
    title = anime["title"]["romaji"]
    year = anime["startDate"]["year"]
    url = anime["siteUrl"]

    embed = discord.Embed(
        title="📅 Ce jour-là dans l'histoire de l'anime",
        description=f"En **{year}**, *[{title}]({url})* sortait le **{day}/{month}** !",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

import matplotlib.pyplot as plt

@bot.command(name="topanime")
async def topanime(ctx):
    now = datetime.now()
    month = now.month
    year = now.year
    if month in [12, 1, 2]: season = "WINTER"
    elif month in [3, 4, 5]: season = "SPRING"
    elif month in [6, 7, 8]: season = "SUMMER"
    else: season = "FALL"

    query = f'''
    query {{
      Page(perPage: 10) {{
        media(season: {season}, seasonYear: {year}, type: ANIME, isAdult: false, sort: SCORE_DESC) {{
          title {{ romaji }}
          averageScore
          siteUrl
        }}
      }}
    }}
    '''
    data = query_anilist(query)

    # Vérifications robustes
    if (
        not data
        or not data.get("data")
        or not data["data"].get("Page")
        or not data["data"]["Page"].get("media")
    ):
        await ctx.send("❌ Impossible de récupérer le top.")
        return

    entries = data["data"]["Page"]["media"]
    desc = ""
    for i, anime in enumerate(entries, 1):
        name = anime.get("title", {}).get("romaji", "Inconnu")
        score = anime.get("averageScore", "??")
        url = anime.get("siteUrl", "")
        desc += f"{i}. [{name}]({url}) – ⭐ {score}\n"

    embed = discord.Embed(title="🔥 Top 10 animés de la saison", description=desc, color=discord.Color.gold())
    await ctx.send(embed=embed)


@bot.command(name="seasonal")
async def seasonal(ctx):
    query = '''
    query {
      Page(perPage: 10) {
        media(type: ANIME, seasonYear: 2025, season: SUMMER, sort: POPULARITY_DESC) {
          title { romaji }
          siteUrl
        }
      }
    }
    '''
    data = query_anilist(query)
    if not data:
        await ctx.send("❌ Erreur AniList.")
        return

    entries = data["data"]["Page"]["media"]
    desc = ""
    for anime in entries:
        desc += f"• [{anime['title']['romaji']}]({anime['siteUrl']})\n"

    embed = discord.Embed(title="🌸 Animes de la saison (été 2025)", description=desc, color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name="search")
async def search_anime(ctx, *, title: str):
    query = '''
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        title { romaji }
        description(asHtml: false)
        siteUrl
        coverImage { large }
        averageScore
      }
    }
    '''
    variables = {"search": title}
    data = query_anilist(query, variables)
    if not data or not data.get("data", {}).get("Media"):
        await ctx.send("❌ Aucun anime trouvé.")
        return

    anime = data["data"]["Media"]
    desc = anime["description"].split(".")[0] + "."

    embed = discord.Embed(
        title=f"🔍 {anime['title']['romaji']}",
        description=f"{desc}\n\n⭐ Score moyen : {anime['averageScore']}",
        color=discord.Color.blue(),
        url=anime["siteUrl"]
    )
    embed.set_image(url=anime["coverImage"]["large"])
    await ctx.send(embed=embed)

@bot.command(name="unlink")
async def unlink(ctx):
    data = load_links()
    user_id = str(ctx.author.id)
    if user_id in data:
        del data[user_id]
        save_links(data)
        await ctx.send("🔗 Ton lien AniList a bien été supprimé.")
    else:
        await ctx.send("❌ Aucun compte AniList n’était lié à ce profil.")


@bot.command(name="mystats")
async def mystats(ctx):
    import requests
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from io import BytesIO
    import os

    def get_badge_file(count):
        if count >= 2000:
            return "1f451.png"
        elif count >= 1600:
            return "1f453.png"
        elif count >= 1300:
            return "1f9e0.png"
        elif count >= 850:
            return "1f525.png"
        elif count >= 400:
            return "1f4fd.png"
        elif count >= 150:
            return "1f4d5.png"
        else:
            return "1f95a.png"

    def emoji_file(name):
        path = f"Emojis/{name}"
        return path if os.path.exists(path) else None

    user_links = load_links()
    user_id = str(ctx.author.id)
    username = user_links.get(user_id)
    if not username:
        await ctx.send("❌ Tu dois lier ton compte avec `!linkanilist <pseudo>` avant d’utiliser cette commande.")
        return

    query = '''
    query ($name: String) {
      User(name: $name) {
        name
        avatar { large }
        bannerImage
        statistics {
          anime {
            count
            minutesWatched
            meanScore
            genres { genre count }
          }
        }
        siteUrl
      }
    }
    '''

    try:
        response = requests.post("https://graphql.anilist.co", json={"query": query, "variables": {"name": username}})
        data = response.json()["data"]["User"]
    except:
        await ctx.send("🚫 Erreur en contactant AniList.")
        return

    stats = data["statistics"]["anime"]
    favorite_genre = max(stats["genres"], key=lambda g: g["count"])["genre"] if stats["genres"] else "N/A"
    avatar_url = data["avatar"]["large"]
    banner_url = data.get("bannerImage")
    site_url = data["siteUrl"]
    count = stats["count"]
    days = round(stats["minutesWatched"] / 1440, 1)
    score = round(stats["meanScore"], 1)

    # Création de l'image
    width, height = 800, 300
    card = Image.new("RGBA", (width, height), (0, 0, 0, 255))

    try:
        banner = Image.open(BytesIO(requests.get(banner_url).content)).resize((width, height)).convert("RGBA")
    except:
        banner = Image.new("RGBA", (width, height), (40, 40, 40, 255))

    blur = banner.filter(ImageFilter.GaussianBlur(3))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 160))
    card = Image.alpha_composite(blur, overlay)

    draw = ImageDraw.Draw(card)
    font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)

    # Avatar
    try:
        avatar = Image.open(BytesIO(requests.get(avatar_url).content)).resize((110, 110)).convert("RGBA")
        mask = Image.new("L", avatar.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 110, 110), fill=255)
        card.paste(avatar, (40, 90), mask)
    except:
        pass

    # Badge
    badge_path = emoji_file(get_badge_file(count))
    if badge_path:
        badge = Image.open(badge_path).resize((48, 48)).convert("RGBA")
        card.paste(badge, (700, 30), badge)

    # Infos
    draw.text((180, 30), f"{data['name']}", font=font_bold, fill="white")

    y = 80
    infos = [
        ("1f4fd.png", f"Animés vus : {count}"),
        ("23f1.png", f"Temps total : {days} jours"),
        ("2b50.png", f"Score moyen : {score}"),
        ("1f3ad.png", f"Genre préféré : {favorite_genre}")
    ]

    for emoji, text in infos:
        icon_path = emoji_file(emoji)
        if icon_path:
            try:
                icon = Image.open(icon_path).resize((28, 28)).convert("RGBA")
                card.paste(icon, (180, y), icon)
            except:
                pass
        draw.text((220, y), text, font=font_text, fill="white")
        y += 35

    draw.text((180, 220), site_url, font=font_text, fill="white")

    # Envoi
    path = f"/tmp/{username}_mystats.png"
    card.save(path)
    with open(path, "rb") as f:
        await ctx.send(file=discord.File(f, filename=f"{username}_mystats.png"))

# Commande pour voir les stats
@bot.command(name="stats")
async def stats(ctx, username: str):
    import requests
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    from io import BytesIO

    query = '''
    query ($name: String) {
      User(name: $name) {
        name
        avatar { large }
        bannerImage
        statistics {
          anime {
            count
            minutesWatched
            meanScore
            genres { genre count }
          }
        }
        siteUrl
      }
    }
    '''
    url = "https://graphql.anilist.co"
    variables = {"name": username}

    try:
        res = requests.post(url, json={"query": query, "variables": variables})
        data = res.json()["data"]["User"]
    except:
        await ctx.send(f"❌ Impossible de récupérer le profil **{username}**.")
        return

    stats = data["statistics"]["anime"]
    genres = stats["genres"]
    fav_genre = sorted(genres, key=lambda g: g["count"], reverse=True)[0]["genre"] if genres else "N/A"
    days = round(stats["minutesWatched"] / 1440, 1)

    avatar = Image.open(BytesIO(requests.get(data["avatar"]["large"]).content)).resize((140, 140)).convert("RGBA")
    banner_url = data["bannerImage"] or "https://s4.anilist.co/file/anilistcdn/media/anime/banner/101922-oJxzcFvSTFZg.jpg"
    banner = Image.open(BytesIO(requests.get(banner_url).content)).resize((800, 300)).convert("RGBA")

    # Effet flou + overlay
    blur = banner.filter(ImageFilter.GaussianBlur(3))
    overlay = Image.new("RGBA", blur.size, (0, 0, 0, 160))
    card = Image.alpha_composite(blur, overlay)

    # Avatar rond avec bord
    mask = Image.new("L", (140, 140), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 140, 140), fill=255)
    avatar = ImageOps.fit(avatar, (140, 140), centering=(0.5, 0.5))
    avatar.putalpha(mask)
    border = Image.new("RGBA", (146, 146), (255, 255, 255, 80))
    border.paste(avatar, (3, 3), avatar)
    card.paste(border, (40, 80), border)

    # Polices
    font1 = ImageFont.truetype("fonts/DejaVuSans-Bold.ttf", 26)
    font2 = ImageFont.truetype("fonts/DejaVuSans.ttf", 20)
    font_badge = ImageFont.truetype("fonts/DejaVuSans.ttf", 20)

    # Texte
    draw = ImageDraw.Draw(card)
    x, y = 210, 30
    draw.text((x, y), data["name"], font=font1, fill="white"); y += 50
    draw.text((x, y), f"🎬 Animés vus : {stats['count']}", font=font2, fill="white"); y += 30
    draw.text((x, y), f"🕒 Temps total : {days} jours", font=font2, fill="white"); y += 30
    draw.text((x, y), f"⭐ Score moyen : {round(stats['meanScore'], 1)}", font=font2, fill="white"); y += 30
    draw.text((x, y), f"🎭 Genre préféré : {fav_genre}", font=font2, fill="white"); y += 30
    draw.text((x, y), f"🔗 {data['siteUrl']}", font=font2, fill="white"); y += 40

    # Badge bonus
    if stats["count"] >= 1000:
        draw.text((x, y), "🏅 Otaku confirmé", font=font_badge, fill="#ffdd55")
    elif stats["meanScore"] >= 85:
        draw.text((x, y), "🌟 Goût d'élite", font=font_badge, fill="#55ddff")

    # Envoi
    output_path = f"/tmp/{username}_styled.png"
    card.save(output_path)

    with open(output_path, "rb") as f:
        await ctx.send(file=discord.File(f, filename=f"{username}_stats.png"))

# Commandes supplémentaires
@bot.command(name="next")
async def next_command(ctx):
    import requests
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from io import BytesIO
    from datetime import datetime

    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    if not episodes:
        await ctx.send("📭 Aucun épisode à venir trouvé dans ta liste.")
        return

    next_ep = min(episodes, key=lambda e: e["airingAt"])
    dt = datetime.fromtimestamp(next_ep["airingAt"], tz=TIMEZONE)
    title = next_ep["title"]
    episode = next_ep["episode"]
    genres = next_ep["genres"]
    image_url = next_ep["image"]

    # 🖼️ Image de fond redimensionnée façon "cover"
    try:
        bg_response = requests.get(image_url)
        img = Image.open(BytesIO(bg_response.content)).convert("RGBA")
        aspect = img.width / img.height
        target_width, target_height = 800, 300

        # Crop pour remplir comme "background-size: cover"
        if aspect > (target_width / target_height):
            # Image plus large → crop horizontal
            new_width = int(img.height * (target_width / target_height))
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            # Image plus haute → crop vertical
            new_height = int(img.width * (target_height / target_width))
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        img = img.resize((target_width, target_height))
    except:
        img = Image.new("RGBA", (800, 300), (30, 30, 30, 255))

    # 🌫️ Flou et overlay sombre
    date_fr = format_datetime(dt, "EEEE d MMMM", locale='fr_FR').capitalize()
    heure = dt.strftime("%H:%M")
    blur = img.filter(ImageFilter.GaussianBlur(3))
    overlay = Image.new("RGBA", blur.size, (0, 0, 0, 160))
    card = Image.alpha_composite(blur, overlay)
    draw = ImageDraw.Draw(card)

    # 📕 Polices
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    
    # 🖋️ Textes
    draw.text((40, 20), "📺 Prochain épisode à venir", font=font_title, fill="white")
    draw.text((40, 70), f"{title} – Épisode {episode}", font=font_text, fill="white")
    draw.text((40, 110), f"Heure : {date_fr} à {heure}", font=font_text, fill="white")
    draw.text((40, 150), "Genres :", font=font_text, fill="white")

    # 🎯 Emojis PNG par genre
    GENRE_EMOJI_FILES = {
        "Action": "1f525.png", "Fantasy": "2728.png", "Romance": "1f496.png",
        "Drama": "1f3ad.png", "Comedy": "1f602.png", "Horror": "1f47b.png",
        "Sci-Fi": "1f680.png", "Slice of Life": "1f338.png", "Sports": "26bd.png",
        "Music": "1f3b5.png", "Supernatural": "1f47e.png", "Mecha": "1f916.png",
        "Psychological": "1f52e.png", "Adventure": "1f30d.png", "Thriller": "1f4a5.png",
        "Ecchi": "1f633.png"
    }

    x_start = 130
    y_genre = 150

    for genre in genres[:4]:
        emoji_file = GENRE_EMOJI_FILES.get(genre)
        text_width = draw.textlength(genre, font=font_text)

        if emoji_file:
            try:
                emoji_img = Image.open(f"Emojis/{emoji_file}").resize((22, 22)).convert("RGBA")
                card.paste(emoji_img, (x_start, y_genre), emoji_img)
                x_start += 28
            except:
                pass

        draw.text((x_start, y_genre), genre, font=font_text, fill="white")
        x_start += int(text_width) + 24

    # 💾 Sauvegarde et envoi
    path = f"/tmp/{ctx.author.id}_next.png"
    card.save(path)
    await ctx.send(file=discord.File(path, filename="next.png"))

    
@bot.command(name="monnext")
async def monnext(ctx):
    import requests
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from io import BytesIO
    from datetime import datetime

    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Tu n’as pas encore lié ton compte AniList. Utilise `!linkanilist <pseudo>`.")
        return

    episodes = get_upcoming_episodes(username)
    if not episodes:
        await ctx.send("📭 Aucun épisode à venir dans ta liste.")
        return

    next_ep = min(episodes, key=lambda e: e["airingAt"])
    dt = datetime.fromtimestamp(next_ep["airingAt"], tz=TIMEZONE)
    title = next_ep["title"]
    episode = next_ep["episode"]
    genres = next_ep["genres"]
    image_url = next_ep["image"]

    # 🖼️ Chargement image et fallback
    try:
        response = requests.get(image_url)
        base_img = Image.open(BytesIO(response.content)).convert("RGBA")

        # Resize proportionnel en gardant le ratio
        base_img.thumbnail((1000, 300), Image.Resampling.LANCZOS)
        bg = Image.new("RGBA", (800, 300), (0, 0, 0, 255))
        x = (800 - base_img.width) // 2
        y = (300 - base_img.height) // 2
        bg.paste(base_img, (x, y))

        blurred = bg.filter(ImageFilter.GaussianBlur(3))
        overlay = Image.new("RGBA", (800, 300), (0, 0, 0, 160))
        card = Image.alpha_composite(blurred, overlay)
    except:
        card = Image.new("RGBA", (800, 300), (20, 20, 20, 255))

    draw = ImageDraw.Draw(card)
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    date_fr = format_datetime(dt, "EEEE d MMMM", locale='fr_FR').capitalize()
    heure = dt.strftime('%H:%M')

    draw.text((40, 25), "🎬 Ton prochain épisode à venir", font=font_title, fill="white")
    draw.text((40, 75), f"{title} – Épisode {episode}", font=font_text, fill="white")
    draw.text((40, 110), f"Heure : {date_fr} à {heure}", font=font_text, fill="white")
    draw.text((40, 150), "Genres :", font=font_text, fill="white")

    # 🎯 Émojis de genres
    GENRE_EMOJI_FILES = {
        "Action": "1f525.png", "Fantasy": "2728.png", "Romance": "1f496.png",
        "Drama": "1f3ad.png", "Comedy": "1f602.png", "Horror": "1f47b.png",
        "Sci-Fi": "1f680.png", "Slice of Life": "1f338.png", "Sports": "26bd.png",
        "Music": "1f3b5.png", "Supernatural": "1f47e.png", "Mecha": "1f916.png",
        "Psychological": "1f52e.png", "Adventure": "1f30d.png", "Thriller": "1f4a5.png",
        "Ecchi": "1f633.png"
    }

    x_start = 130
    y_emoji = 150

    for genre in genres[:4]:
        emoji_file = GENRE_EMOJI_FILES.get(genre)
        text_width = draw.textlength(genre, font=font_text)

        if emoji_file:
            try:
                emoji_img = Image.open(f"Emojis/{emoji_file}").resize((22, 22)).convert("RGBA")
                card.paste(emoji_img, (x_start, y_emoji - 2), emoji_img)
                x_start += 26
            except:
                pass

        draw.text((x_start, y_emoji), genre, font=font_text, fill="white")
        x_start += int(text_width) + 24

    path = f"/tmp/{ctx.author.id}_monnext.png"
    card.save(path)
    await ctx.send(file=discord.File(path, filename="monnext.png"))

@bot.command(name="monplanning")
async def mon_planning(ctx):
    from babel.dates import format_datetime

    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Tu n’as pas encore lié ton compte AniList. Utilise `!linkanilist <pseudo>`.")
        return

    episodes = get_upcoming_episodes(username)
    if not episodes:
        await ctx.send(f"📭 Aucun épisode à venir trouvé pour **{username}**.")
        return

    embed = discord.Embed(
        title=f"📅 Planning personnel – {username}",
        description="Voici les prochains épisodes à venir dans ta liste.",
        color=discord.Color.teal()
    )
    
    # Première boucle : ajout des épisodes
    for ep in sorted(episodes, key=lambda e: e["airingAt"])[:10]:
        dt = datetime.fromtimestamp(ep["airingAt"], tz=TIMEZONE)
        emoji = genre_emoji(ep["genres"])
        date_fr = format_datetime(dt, "EEEE d MMMM", locale='fr_FR').capitalize()
        heure = dt.strftime('%H:%M')
        value = f"🕒 {date_fr} à {heure}"

        embed.add_field(
            name=f"{emoji} {ep['title']} – Épisode {ep['episode']}",
            value=value,
            inline=False
        )

    # Deuxième boucle : miniature sur le premier
    for i, ep in enumerate(sorted(episodes, key=lambda e: e["airingAt"])[:10]):
        if i == 0:
            embed.set_thumbnail(url=ep["image"])
            break  # plus besoin de continuer après le premier

    await ctx.send(embed=embed)

@bot.command(name="monchart")
async def monchart(ctx, username: str = None):
    links = load_links()
    if not username:
        username = links.get(str(ctx.author.id))
        if not username:
            await ctx.send("❌ Tu dois lier ton compte AniList avec `!linkanilist <pseudo>`.")
            return

    query = '''
    query ($name: String) {
      User(name: $name) {
        statistics {
          anime {
            genres {
              genre
              count
            }
          }
        }
      }
    }
    '''
    data = query_anilist(query, {"name": username})
    if not data:
        await ctx.send("❌ Impossible de récupérer les données AniList.")
        return

    genre_stats = data["data"]["User"]["statistics"]["anime"]["genres"]
    top_genres = sorted(genre_stats, key=lambda g: g["count"], reverse=True)[:6]
    total = sum(g["count"] for g in top_genres)

    def emoji_genre(name):
        emojis = {
            "Action": "⚔️", "Fantasy": "🧙", "Romance": "💖", "Comedy": "😂",
            "Drama": "🎭", "Horror": "👻", "Sci-Fi": "🚀", "Music": "🎵",
            "Sports": "⚽", "Slice of Life": "🍃", "Psychological": "🧠",
            "Adventure": "🌍", "Mecha": "🤖", "Supernatural": "🔮",
            "Ecchi": "😳", "Mystery": "🕵️"
        }
        return emojis.get(name, "📺")

    def bar(p):
        filled = int(p / 10)
        return "▰" * filled + "▱" * (10 - filled)

    lines = [f"📊 Genres les plus regardés de **{username}** :\n"]
    for g in top_genres:
        percent = int((g["count"] / total) * 100)
        lines.append(f"{emoji_genre(g['genre'])} {g['genre']:<13} {bar(percent)}  {percent}%")

    await ctx.send("\n".join(lines))

@bot.command(name="uptime")
async def uptime(ctx):
    now = datetime.utcnow()
    uptime_duration = now - start_time

    hours, remainder = divmod(int(uptime_duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    desc = f"🕒 **AnimeBot actif depuis :** {hours} heures, {minutes} minutes"
    embed = discord.Embed(title="Uptime du bot", description=desc, color=0x2ecc71)
    await ctx.send(embed=embed)

    
@bot.command(name="journalier")
async def journalier(ctx, mode: str = ""):
    uid = str(ctx.author.id)
    user_settings.setdefault(uid, {})
    if mode.lower() in ["off", "disable", "désactiver"]:
        user_settings[uid]["daily_summary"] = False
        save_json(USER_SETTINGS_FILE, user_settings)
        await ctx.send("📭 Résumé quotidien désactivé pour toi.")
    elif mode.lower() in ["on", "enable", "activer"]:
        user_settings[uid]["daily_summary"] = True
        save_json(USER_SETTINGS_FILE, user_settings)
        await ctx.send("📬 Tu recevras désormais un résumé **chaque matin en message privé**.")
    else:
        current = user_settings.get(uid, {}).get("daily_summary", False)
        emoji = "📬" if current else "📭"
        await ctx.send(f"{emoji} Le résumé quotidien est **{'activé' if current else 'désactivé'}** pour toi.")

@bot.command(name="aujourdhui")
async def aujourdhui(ctx):
    today = datetime.now(TIMEZONE).date()
    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    found = [(ep, datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE))
             for ep in episodes if datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE).date() == today]
    if not found:
        await ctx.send("Aucun épisode prévu aujourd’hui.")
        return
    embed = discord.Embed(title="📅 Épisodes du jour", color=discord.Color.green())
    for ep, dt in found:
        emoji = genre_emoji(ep["genres"])
        embed.add_field(name=f"{emoji} {ep['title']} — Ép {ep['episode']}", value=dt.strftime("%H:%M"), inline=False)
    await ctx.send(embed=embed)

@bot.command(name="planning")
async def planning(ctx):
    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    if not episodes:
        await ctx.send("Aucun planning disponible.")
        return

    weekdays = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    planning = {day: [] for day in weekdays}

    for ep in episodes:
        day = datetime.fromtimestamp(ep['airingAt']).strftime('%A')
        fr_day = {
            'Monday': 'Lundi', 'Tuesday': 'Mardi', 'Wednesday': 'Mercredi',
            'Thursday': 'Jeudi', 'Friday': 'Vendredi', 'Saturday': 'Samedi', 'Sunday': 'Dimanche'
        }[day]
        dt = datetime.fromtimestamp(ep['airingAt']).strftime("%H:%M")
        planning[fr_day].append(f"• {ep['title']} — Ép. {ep['episode']} ({dt})")

    for day in weekdays:
        if planning[day]:
            embed = discord.Embed(title=f"📅 Planning du {day}", description="\n".join(planning[day]), color=0x1abc9c)
            await ctx.send(embed=embed)

@bot.command(name="animequiz")
async def anime_quiz(ctx, difficulty: str = "normal"):
    await ctx.send("🎮 Préparation du quiz...")

    difficulty = difficulty.lower()
    sort_option = "SCORE_DESC"
    if difficulty == "easy":
        sort_option = "POPULARITY_DESC"
    elif difficulty == "hard":
        sort_option = "TRENDING_DESC"

    anime = None
    for _ in range(10):
        page = random.randint(1, 500)
        query = f'''
        query {{
          Page(perPage: 1, page: {page}) {{
            media(type: ANIME, isAdult: false, sort: {sort_option}) {{
              id
              title {{ romaji english native }}
              coverImage {{ large }}
            }}
          }}
        }}
        '''
        data = query_anilist(query)
        try:
            anime = data["data"]["Page"]["media"][0]
            break
        except:
            continue

    if not anime:
        await ctx.send("❌ Aucun anime trouvé.")
        return

    correct_titles = set()

    anime_id = str(anime.get("id"))
    if anime_id in title_cache:
        correct_titles = set(title_cache[anime_id])
    else:
        correct_titles = title_variants(anime["title"])  # fallback au cas où



    # 🎴 Embed visuel
    embed = discord.Embed(
        title="❓ Quel est cet anime ?",
        description="Tu as **20 secondes** pour deviner. Tape `jsp` si tu veux passer.",
        color=discord.Color.orange()
    )
    embed.set_image(url=anime["coverImage"]["large"])
    await ctx.send(embed=embed)

    def check(m):
        return (
            m.author == ctx.author and
            m.channel == ctx.channel
        )

    try:
        msg = await bot.wait_for("message", timeout=20.0, check=check)
        user_input = normalize(msg.content)

        if user_input == "jsp":
            await ctx.send(f"⏭️ Question passée. La bonne réponse était **{anime['title']['romaji']}**.")
            return

        if user_input in correct_titles:
            await ctx.send(f"✅ Bonne réponse, **{ctx.author.display_name}** !")

            # 🎯 Score + XP
            scores = load_scores()
            uid = str(ctx.author.id)
            scores[uid] = scores.get(uid, 0) + 1
            save_scores(scores)

            xp_amount = 10
            if difficulty == "easy":
                xp_amount = 5
            elif difficulty == "hard":
                xp_amount = 15
            add_xp(ctx.author.id, amount=xp_amount)

        else:
            await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title']['romaji']}**.")

    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était **{anime['title']['romaji']}**.")

@bot.command(name="animequizmulti")
async def anime_quiz_multi(ctx, nb_questions: int = 5):
    if nb_questions < 1 or nb_questions > 20:
        await ctx.send("❌ Tu dois choisir un nombre entre 1 et 20.")
        return

    await ctx.send(f"🎮 Lancement de **{nb_questions} questions** pour **{ctx.author.display_name}**...")

    difficulties = ["easy", "normal", "hard"]
    score = 0
    total_xp = 0

    for i in range(nb_questions):
        difficulty = random.choice(difficulties)
        sort_option = {
            "easy": "POPULARITY_DESC",
            "normal": "SCORE_DESC",
            "hard": "TRENDING_DESC"
        }.get(difficulty, "SCORE_DESC")

        anime = None
        for _ in range(10):
            page = random.randint(1, 500)
            query = f'''
            query {{
              Page(perPage: 1, page: {page}) {{
                media(type: ANIME, isAdult: false, sort: {sort_option}) {{
                  id
                  title {{ romaji english native }}
                  coverImage {{ large }}
                }}
              }}
            }}
            '''
            data = query_anilist(query)
            try:
                anime = data["data"]["Page"]["media"][0]
                break
            except:
                continue

        if not anime:
            await ctx.send("❌ Impossible de récupérer un anime.")
            continue

        correct_titles = title_variants(anime["title"])
        image = anime["coverImage"]["large"]

        embed = discord.Embed(
            title=f"❓ Question {i+1}/{nb_questions} — difficulté `{difficulty}`",
            description="Tu as **20 secondes** pour deviner. Tape `jsp` pour passer.",
            color=discord.Color.orange()
        )
        embed.set_image(url=image)
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=20.0, check=check)
            guess = normalize(msg.content)

            if guess == "jsp":
                await ctx.send(f"⏭️ Passé. C’était **{anime['title']['romaji']}**.")
                continue

            if guess in correct_titles:
                await ctx.send(f"✅ Bonne réponse !")
                score += 1
                xp_gain = 5 if difficulty == "easy" else 10 if difficulty == "normal" else 15
                total_xp += xp_gain
            else:
                await ctx.send(f"❌ Faux ! C’était **{anime['title']['romaji']}**.")

        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé ! C’était **{anime['title']['romaji']}**.")

        await asyncio.sleep(1.5)

    # Enregistrement du score global
    scores = load_scores()
    uid = str(ctx.author.id)

    # Pénalité si moins de 50% de bonnes réponses
    if score < (nb_questions // 2):
        penalty = 1
        scores[uid] = max(0, scores.get(uid, 0) - penalty)
        await ctx.send(f"⚠️ Tu as fait moins de 50% de bonnes réponses, -{penalty} point retiré.")
    else:
        scores[uid] = scores.get(uid, 0) + score

    save_scores(scores)
    add_xp(ctx.author.id, amount=total_xp)

    await ctx.send(f"🏁 Fin du quiz ! Score final : **{score}/{nb_questions}** – 🎖️ XP gagné : **{total_xp}**")

@bot.command(name="duel")
async def duel(ctx, opponent: discord.Member):
    if opponent.bot:
        await ctx.send("🤖 Tu ne peux pas défier un bot.")
        return
    if opponent == ctx.author:
        await ctx.send("🙃 Tu ne peux pas te défier toi-même.")
        return

    await ctx.send(f"⚔️ Duel entre **{ctx.author.display_name}** et **{opponent.display_name}** lancé !")

    players = [ctx.author, opponent]
    scores = {ctx.author.id: 0, opponent.id: 0}
    difficulties = ["easy", "normal", "hard"]

    for i in range(1, 4):
        await ctx.send(f"❓ Question {i}/3...")

        # 🎯 Tirage aléatoire d’un anime
        difficulty = random.choice(difficulties)
        sort_option = {
            "easy": "POPULARITY_DESC",
            "normal": "SCORE_DESC",
            "hard": "TRENDING_DESC"
        }[difficulty]

        anime = None
        for _ in range(10):
            page = random.randint(1, 500)
            query = f'''
            query {{
              Page(perPage: 1, page: {page}) {{
                media(type: ANIME, isAdult: false, sort: {sort_option}) {{
                  id
                  title {{ romaji english native }}
                  coverImage {{ large }}
                }}
              }}
            }}
            '''
            data = query_anilist(query)
            try:
                anime = data["data"]["Page"]["media"][0]
                break
            except:
                continue

        if not anime:
            await ctx.send("❌ Impossible de récupérer un anime.")
            continue

        correct_titles = title_variants(anime["title"])
        embed = discord.Embed(
            title=f"🎮 Duel – Question {i}/3",
            description="**Tu as 15 secondes** pour deviner l’anime. Tape `jsp` pour passer.",
            color=discord.Color.red()
        )
        embed.set_image(url=anime["coverImage"]["large"])
        await ctx.send(embed=embed)

        def check(m):
            return (
                m.channel == ctx.channel and
                m.author in players
            )

        try:
            msg = await bot.wait_for("message", timeout=15.0, check=check)
            content = normalize(msg.content)

            if content == "jsp":
                await ctx.send(f"⏭️ Question passée. C’était **{anime['title']['romaji']}**.")
                continue

            if content in correct_titles:
                scores[msg.author.id] += 1
                await ctx.send(f"✅ Bonne réponse de **{msg.author.display_name}** !")
            else:
                await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title']['romaji']}**.")
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé ! C’était **{anime['title']['romaji']}**.")

        await asyncio.sleep(1)

    # 🧾 Résultat final
    s1 = scores[ctx.author.id]
    s2 = scores[opponent.id]
    if s1 == s2:
        result = f"🤝 Égalité parfaite : {s1} - {s2}"
    else:
        winner = ctx.author if s1 > s2 else opponent
        loser = opponent if winner == ctx.author else ctx.author
        result = f"🏆 Victoire de **{winner.display_name}** ({s1} - {s2})"
        add_xp(winner.id, amount=20)

    await ctx.send(result)

@bot.command(name="suggest")
async def suggest(ctx, genre: str = None):
    query = '''
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME, status: PLANNING) {
        lists {
          entries {
            media {
              title {
                romaji
              }
              genres
              coverImage {
                large
              }
              siteUrl
            }
          }
        }
      }
    }
    '''

    variables = {
        "name": ANILIST_USERNAME
    }

    response = requests.post('https://graphql.anilist.co', json={'query': query, 'variables': variables})
    data = response.json()

    # On récupère tous les animés dans la liste "à regarder"
    entries = []
    try:
        for l in data["data"]["MediaListCollection"]["lists"]:
            entries.extend(l["entries"])
    except Exception:
        await ctx.send("❌ Impossible de récupérer ta liste Anilist.")
        return

    # Filtrage par genre si demandé
    if genre:
        genre = genre.capitalize()
        entries = [e for e in entries if genre in e["media"]["genres"]]

    if not entries:
        await ctx.send("❌ Aucun animé trouvé dans ta liste correspondante.")
        return

    # Sélection aléatoire
    choice = random.choice(entries)
    media = choice["media"]

    embed = discord.Embed(
        title=f"🎲 Suggestion : {media['title']['romaji']}",
        description=f"📚 [Voir sur AniList]({media['siteUrl']})",
        color=discord.Color.blurple()
    )
    embed.set_image(url=media["coverImage"]["large"])
    embed.set_footer(text=f"Genres : {', '.join(media['genres'])}")

    await ctx.send(embed=embed)

@bot.command(name="planningvisuel")
async def planningvisuel(ctx):
    import calendar
    from PIL import Image, ImageDraw, ImageFont
    from datetime import datetime, timedelta
    import pytz

    # 📅 Récupération des épisodes à venir
    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    TIMEZONE = pytz.timezone("Europe/Paris")
    jours = list(calendar.day_name)
    planning = {day: [] for day in jours}

    for ep in episodes:
        dt = datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE)
        day = dt.strftime("%A")
        planning[day].append({
            "title": ep["title"],
            "episode": ep["episode"],
            "time": dt.strftime("%H:%M")
        })

    # 🖼️ Création de l’image
    width, height = 800, 600
    card = Image.new("RGB", (width, height), (30, 30, 40))
    draw = ImageDraw.Draw(card)

    # Polices
    font_title = ImageFont.truetype("fonts/DejaVuSans-Bold.ttf", 28)
    font_day = ImageFont.truetype("fonts/DejaVuSans-Bold.ttf", 22)
    font_text = ImageFont.truetype("fonts/DejaVuSans.ttf", 18)

    # En-tête
    draw.text((20, 20), "Planning des épisodes – Semaine", font=font_title, fill="white")

    # Placement
    x, y = 40, 70
    for day in jours:
        draw.text((x, y), f"> {day}", font=font_day, fill="#ffdd77")
        y += 30
        for ep in planning[day][:4]:  # max 4 par jour
            draw.text((x + 10, y), f"• {ep['title']} – Ep {ep['episode']} ({ep['time']})", font=font_text, fill="white")
            y += 24
        y += 30

    # Sauvegarde et envoi
    path = f"/tmp/planning_week.png"
    card.save(path)

    with open(path, "rb") as f:
        await ctx.send(file=discord.File(f, filename="planning.png"))

    
@bot.command(name="help")
async def help_command(ctx):
    import asyncio

    pages = [
        {
            "title": "📅 Épisodes & Planning + 🔔 Notifications",
            "fields": [
                ("`!next` / `!monnext`", "Prochain épisode dans ta liste ou celle d'un membre."),
                ("`!planning` / `!monplanning`", "Planning complet de la semaine."),
                ("`!prochains <genre>`", "Épisodes à venir filtrés par genre."),
                ("`!planningvisuel`", "Affiche une version visuelle du planning."),
                ("`!reminder`", "Active ou désactive les rappels quotidiens."),
                ("`!setalert HH:MM`", "Définit l’heure de ton résumé automatique."),
                ("`!anitracker <titre>`", "Suis un anime et reçois une alerte DM."),
                ("`!anitracker list` / `remove <titre>`", "Voir ou retirer tes suivis.")
            ]
        },
        {
            "title": "🎮 Quiz & Niveaux + 🏆 Challenges",
            "fields": [
                ("`!animequiz`", "Devine un anime en solo."),
                ("`!animequizmulti <N>`", "Enchaîne N questions à difficulté aléatoire."),
                ("`!duel @ami`", "Affronte un ami en duel de 3 questions."),
                ("`!animebattle`", "Petit mode quiz solo (aléatoire rapide)."),
                ("`!quiztop`", "Classement des meilleurs au quiz."),
                ("`!myrank`", "Affiche ton niveau, XP et ton titre."),
                ("`!anichallenge`", "Reçois un anime à regarder et note-le."),
                ("`!challenge complete <note>`", "Indique que tu as terminé ton défi."),
                ("`!weekly`", "Un nouveau défi chaque semaine."),
                ("`!weekly complete`", "Valide ton défi hebdomadaire.")
            ]
        },
        {
            "title": "📊 Stats & Profils + 🎯 Comparaison",
            "fields": [
                ("`!linkanilist <pseudo>`", "Lier ton compte AniList au bot."),
                ("`!unlink`", "Supprimer le lien avec ton compte AniList."),
                ("`!mystats` / `!stats <pseudo>`", "Carte de profil stylisée (toi ou un autre)."),
                ("`!mychart` / `!monchart`", "Répartition de tes genres préférés."),
                ("`!duelstats @ami`", "Compare ton profil AniList à un ami."),
                ("`!classementgenre <genre>`", "Classement des passionnés par genre.")
            ]
        },
        {
            "title": "🛠️ Utilitaires & Recherche",
            "fields": [
                ("`!uptime`", "Depuis combien de temps le bot est actif."),
                ("`!setchannel`", "Définit ce salon comme canal des notifications."),
                ("`!topanime`", "Top des animés les mieux notés."),
                ("`!seasonal`", "Top des animés en cours cette saison."),
                ("`!search <titre>`", "Recherche un anime via AniList."),
                ("`!help`", "Affiche cette aide interactive.")
            ]
        }
    ]

    def make_embed(index):
        page = pages[index]
        embed = discord.Embed(
            title=page["title"],
            color=discord.Color.purple()
        )
        for name, desc in page["fields"]:
            embed.add_field(name=name, value=desc, inline=False)
        embed.set_footer(text=f"Page {index+1}/{len(pages)} — AnimeBot")
        return embed

    current = 0
    message = await ctx.send(embed=make_embed(current))
    await message.add_reaction("◀️")
    await message.add_reaction("▶️")

    def check(reaction, user):
        return (
            user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"]
            and reaction.message.id == message.id
        )

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=120.0, check=check)
            if str(reaction.emoji) == "▶️":
                current = (current + 1) % len(pages)
            elif str(reaction.emoji) == "◀️":
                current = (current - 1) % len(pages)
            await message.edit(embed=make_embed(current))
            await message.remove_reaction(reaction, user)
        except asyncio.TimeoutError:
            break

@bot.command(name="resetquiz")
@commands.is_owner()
async def reset_quiz(ctx):
    scores = load_scores()
    if scores:
        top_uid = max(scores.items(), key=lambda x: x[1])[0]
        winner_data = {
            "uid": top_uid,
            "timestamp": datetime.now(tz=TIMEZONE).isoformat()
        }
        save_json("last_quiz_winner.json", winner_data)
    save_scores({})
    await ctx.send("✅ Classement `animequiz` réinitialisé.")

@bot.command(name="setalert")
async def setalert(ctx, time_str: str):
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError

        # Tu stockes l'heure dans ton système de préférences
        user_id = str(ctx.author.id)
        preferences.setdefault(user_id, {})
        preferences[user_id]["alert_time"] = f"{hour:02d}:{minute:02d}"
        save_json(PREFERENCES_FILE, preferences)

        await ctx.send(f"✅ Alerte quotidienne définie à **{hour:02d}:{minute:02d}**.")
    except ValueError:
        await ctx.send("❌ Format invalide. Utilise `!setalert HH:MM` (ex: `!setalert 08:30`).")

    
@bot.command(name="reminder")
async def reminder(ctx, mode: str = ""):
    uid = str(ctx.author.id)
    if mode.lower() in ["off", "disable", "désactiver"]:
        user_settings.setdefault(uid, {})
        user_settings[uid]["reminder"] = False
        save_json(USER_SETTINGS_FILE, user_settings)
        await ctx.send("🔕 Rappels désactivés pour toi.")
    elif mode.lower() in ["on", "enable", "activer"]:
        user_settings.setdefault(uid, {})
        user_settings[uid]["reminder"] = True
        save_json(USER_SETTINGS_FILE, user_settings)
        await ctx.send("🔔 Rappels activés pour toi.")
    else:
        current = user_settings.get(uid, {}).get("reminder", True)
        emoji = "🔔" if current else "🔕"
        await ctx.send(f"{emoji} Les rappels sont actuellement **{'activés' if current else 'désactivés'}** pour toi.")

@bot.command(name="setchannel")
async def setchannel(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("🚫 Tu n’as pas la permission d’utiliser cette commande.")
        return
    config = get_config()
    config["channel_id"] = ctx.channel.id
    save_config(config)
    await ctx.send(f"✅ Ce canal a été défini pour les notifications.")

@tasks.loop(minutes=1)
async def send_daily_summaries():
    now = datetime.now(TIMEZONE)
    current_time = now.strftime("%H:%M")
    current_day = now.strftime("%A")

    for user_id, prefs in preferences.items():
        if not prefs.get("reminder", True):
            continue  # L'utilisateur a désactivé les reminders

        alert_time = prefs.get("alert_time", "08:00")
        if current_time != alert_time:
            continue  # Ce n’est pas encore l’heure

        episodes = get_upcoming_episodes(ANILIST_USERNAME)
        episodes_today = [ep for ep in episodes if
                          datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE).strftime("%A") == current_day]

        if not episodes_today:
            continue

        try:
            user = await bot.fetch_user(int(user_id))
            embed = discord.Embed(
                title="📺 Résumé du jour",
                description=f"Voici les épisodes à regarder ce **{jours_fr.get(current_day, current_day)}** !",
                color=discord.Color.green()
            )
            for ep in sorted(episodes_today, key=lambda e: e['airingAt']):
                dt = datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE)
                emoji = genre_emoji(ep["genres"])
                embed.add_field(
                    name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                    value=f"🕒 {dt.strftime('%H:%M')}",
                    inline=False
                )

            await user.send(embed=embed)
        except Exception as e:
            print(f"[Erreur DM résumé pour {user_id}] {e}")

@tasks.loop(hours=1)
async def reset_monthly_scores():
    # Ton code de remise à zéro
    print("🔁 Reset des scores mensuels exécuté")
    
@tasks.loop(hours=24)
async def monthly_reset():
    now = datetime.now(tz=TIMEZONE)
    if now.day == 1:
        scores = load_scores()
        if scores:
            top_uid = max(scores.items(), key=lambda x: x[1])[0]
            winner_data = {
                "uid": top_uid,
                "timestamp": now.isoformat()
            }
            save_json("last_quiz_winner.json", winner_data)
            save_scores({})  # reset scores
            print("🔁 Quiz mensuel réinitialisé.")

            config = get_config()
            cid = config.get("channel_id")
            if cid:
                channel = bot.get_channel(cid)
                if channel:
                    try:
                        user = await bot.fetch_user(int(top_uid))
                        await channel.send(
                            f"🔁 **Début du mois !** Le classement `!quiztop` a été remis à zéro !\n"
                            f"🏆 Bravo à **{user.display_name}** pour sa victoire le mois dernier ! Bonne chance à tous 🍀"
                        )
                    except:
                        pass

@tasks.loop(minutes=5)
async def check_new_episodes():
    await bot.wait_until_ready()
    config = get_config()
    cid = config.get("channel_id")
    if cid is None:
        return
    channel = bot.get_channel(cid)
    if not channel:
        return

    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    now = int(datetime.now(tz=pytz.utc).timestamp())

    for ep in episodes:
        uid = f"{ep['id']}-{ep['episode']}"
        if uid in notified:
            continue
        if now >= ep["airingAt"] - 900:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE)
            embed = build_embed(ep, dt)
            await channel.send("🔔 Rappel d'épisode imminent :", embed=embed)
            notified.add(uid)
            save_json(NOTIFIED_FILE, list(notified))

            # ✅ Envoi aux abonnés
            tracker_data = load_tracker()
            for uid, titles in tracker_data.items():
                if normalize(ep["title"]) in [normalize(t) for t in titles]:
                    try:
                        user = await bot.fetch_user(int(uid))
                        await user.send(
                            f"🔔 Nouvel épisode dispo : **{ep['title']} – Épisode {ep['episode']}**",
                            embed=embed
                        )
                    except:
                        pass  # utilisateur bloqué, DM désactivés, etc.

            
@bot.event
async def on_ready():
    now = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
    print(f"[BOOT 🟢] {bot.user.name} prêt — ID: {bot.user.id} à {now}")

    # Mise à jour du cache de titres (dans un thread séparé si nécessaire)
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, update_title_cache)

    # Récupération du bon channel depuis la config
    config = get_config()
    channel_id = config.get("channel_id")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                await channel.send("🤖 AnimeBot a démarré et est prêt à traquer les sorties !")
            except:
                pass

    # ✅ Tâche 1 : résumé quotidien
    if not send_daily_summaries.is_running():
        send_daily_summaries.start()

    # ✅ Tâche 2 : alertes épisodes
    if not check_new_episodes.is_running():
        check_new_episodes.start()

    if not reset_monthly_scores.is_running():
        reset_monthly_scores.start()

    if not monthly_reset.is_running():
        monthly_reset.start()


# Lancer le bot
bot.run(DISCORD_TOKEN)

