# AnimeBot — Version finale avec !setchannel, préférences, alertes, !prochains stylisé
import discord
from discord.ext import commands, tasks
import requests
import json
import random
import asyncio
import os
import pytz
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import unicodedata
import matplotlib.pyplot as plt

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

for path in [
    PREFERENCES_FILE, QUIZ_SCORES_FILE, TRACKER_FILE, WEEKLY_FILE,
    LINKED_FILE, LEVELS_FILE, CHALLENGES_FILE,
    USER_SETTINGS_FILE, NOTIFIED_FILE, LINKS_FILE
]:
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)

for path in [
    PREFERENCES_FILE, QUIZ_SCORES_FILE, "/data/anitracker.json", "/data/weekly.json",
    "/data/linked_users.json", "/data/quiz_levels.json", "/data/challenges.json",
    USER_SETTINGS_FILE, NOTIFIED_FILE, LINKS_FILE
]:
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)

def normalize(text):
    if not text:
        return ""
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')  # Enlève les accents
    return ''.join(e for e in text.lower() if e.isalnum() or e.isspace())

def title_variants(title_data):
    titles = set()
    for key in ['romaji', 'english', 'native']:
        t = title_data.get(key)
        if t:
            titles.add(normalize(t))
            short = t.split(":")[0].split("-")[0].strip()
            titles.add(normalize(short))
    return titles

# 📁 Chargement des préférences utilisateur
PREFERENCES_FILE = "/data/preferences.json"

QUIZ_SCORES_FILE = "/data/quiz_scores.json"

def get_user_anilist(user_id):
    data = load_links()
    return data.get(str(user_id))

def load_tracker():
    try:
        with open("/data/anitracker.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_tracker(data):
    with open("/data/anitracker.json", "w") as f:
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

def load_json(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
                    "genres": media.get("genres", [])
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
            embed.add_field(
                name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                value=f"🗓️ {jours_fr[dt.strftime('%A')]} {dt.strftime('%d/%m')} à {dt.strftime('%H:%M')}",
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
    scores = load_scores()
    if not scores:
        await ctx.send("🏆 Aucun score enregistré pour l’instant.")
        return

    # Titres évolutifs par score (tous les 5 points)
    def get_title(score):
        if score >= 50:
            return "🧠 Grand Sage"
        elif score >= 45:
            return "👑 Champion du quiz"
        elif score >= 40:
            return "🌟 Stratège de l'anime"
        elif score >= 35:
            return "🎯 Expert en animation"
        elif score >= 30:
            return "🎬 Analyste Otaku"
        elif score >= 25:
            return "🔥 Fan Hardcore"
        elif score >= 20:
            return "📺 Binge-watcheur"
        elif score >= 15:
            return "💡 Connaisseur"
        elif score >= 10:
            return "📘 Passionné"
        elif score >= 5:
            return "🌱 Débutant prometteur"
        else:
            return "🔰 Nouveau joueur"

    leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
    desc = ""

    for i, (uid, score) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(int(uid))
            title = get_title(score)
            desc += f"{i}. **{user.display_name}** — {score} pts {title}\n"
        except:
            continue  # Si l'utilisateur n'existe plus

    embed = discord.Embed(
        title="🏆 Classement Anime Quiz",
        description=desc,
        color=discord.Color.gold()
    )
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

        bonnes_reponses = title_variants(anime["title"])

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

@bot.command(name="mychart")
async def mychart(ctx, username: str):
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
        await ctx.send("❌ Erreur lors de la récupération.")
        return

    genres = data["data"]["User"]["statistics"]["anime"]["genres"]
    genres = sorted(genres, key=lambda g: g["count"], reverse=True)[:8]

    labels = [g["genre"] for g in genres]
    sizes = [g["count"] for g in genres]

    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%')
    plt.title(f"Genres préférés de {username}")

    path = f"/tmp/{username}_chart.png"
    plt.savefig(path)
    plt.close()

    await ctx.send(file=discord.File(path))

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
    data = load_links()
    user_id = str(ctx.author.id)
    pseudo = data.get(user_id)

    if not pseudo:
        await ctx.send("❌ Tu n’as pas encore lié ton compte AniList.\nUtilise `!linkanilist <pseudo>` pour le faire.")
        return

    await stats(ctx, pseudo)

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
    episodes = get_upcoming_episodes(ANILIST_USERNAME)

    if not episodes:
        await ctx.send("📭 Aucun épisode à venir trouvé dans ta liste.")
        return

    # 🔽 On trie par date la plus proche
    next_ep = min(episodes, key=lambda e: e["airingAt"])

    dt = datetime.fromtimestamp(next_ep["airingAt"], tz=TIMEZONE)
    title = next_ep["title"]
    episode = next_ep["episode"]
    emoji = genre_emoji(next_ep["genres"])

    embed = discord.Embed(
        title="🎬 Prochain épisode à sortir",
        description=f"**{title}** — Épisode {episode}",
        color=discord.Color.orange()
    )
    embed.add_field(name="🕒 Horaire", value=dt.strftime("%A %d %B à %H:%M"), inline=False)
    embed.add_field(name="🎭 Genre", value=", ".join(next_ep["genres"]), inline=False)
    embed.set_footer(text="AnimeBot – AniList Sync")
    
    embed.set_thumbnail(url=next_ep["image"])
    await ctx.send(embed=embed)

@bot.command(name="monnext")
async def mon_next(ctx):
    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Tu n’as pas encore lié ton compte AniList. Utilise `!linkanilist <pseudo>`.")
        return

    episodes = get_upcoming_episodes(username)
    if not episodes:
        await ctx.send(f"📭 Aucun épisode à venir trouvé pour **{username}**.")
        return

    next_ep = min(episodes, key=lambda e: e["airingAt"])
    dt = datetime.fromtimestamp(next_ep["airingAt"], tz=TIMEZONE)
    emoji = genre_emoji(next_ep["genres"])

    embed = discord.Embed(
        title=f"🎬 Prochain épisode pour {username}",
        description=f"**{next_ep['title']}** — Épisode {next_ep['episode']}",
        color=discord.Color.blue()
    )
    embed.add_field(name="🕒 Horaire", value=dt.strftime("%A %d %B à %H:%M"), inline=False)
    embed.add_field(name="🎭 Genre", value=", ".join(next_ep["genres"]), inline=False)
    embed.set_thumbnail(url=next_ep["image"])
    embed.set_footer(text="AnimeBot – AniList perso ❤️")

    await ctx.send(embed=embed)

@bot.command(name="monplanning")
async def mon_planning(ctx):
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
    
    for ep in sorted(episodes, key=lambda e: e["airingAt"])[:10]:
        dt = datetime.fromtimestamp(ep["airingAt"], tz=TIMEZONE)
        emoji = genre_emoji(ep["genres"])
        embed.add_field(
            name=f"{emoji} {ep['title']} – Épisode {ep['episode']}",
            value=f"🕒 {dt.strftime('%A %d %B à %H:%M')}",
            inline=False
        )
        
    for i, ep in enumerate(sorted(episodes, key=lambda e: e["airingAt"])[:10]):
        dt = datetime.fromtimestamp(ep["airingAt"], tz=TIMEZONE)
        emoji = genre_emoji(ep["genres"])
        embed.add_field(
            name=f"{emoji} {ep['title']} – Épisode {ep['episode']}",
            value=f"🕒 {dt.strftime('%A %d %B à %H:%M')}",
            inline=False
        )

        if i == 0:
            embed.set_thumbnail(url=ep["image"])  # ✅ Ajoute l'image du 1er

    await ctx.send(embed=embed)

@bot.command(name="monchart")
async def mon_chart(ctx):
    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Tu dois lier ton compte avec `!linkanilist`.")
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
    variables = {"name": username}
    url = "https://graphql.anilist.co"

    try:
        res = requests.post(url, json={"query": query, "variables": variables})
        data = res.json()
        genres = data["data"]["User"]["statistics"]["anime"]["genres"]
        genres = sorted(genres, key=lambda g: g["count"], reverse=True)[:8]

        labels = [g["genre"] for g in genres]
        sizes = [g["count"] for g in genres]

        fig, ax = plt.subplots()
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=140)
        ax.axis("equal")
        plt.title(f"Répartition des genres — {username}")

        img_path = f"/tmp/{username}_chart.png"
        plt.savefig(img_path)
        plt.close()

        with open(img_path, "rb") as f:
            await ctx.send(file=discord.File(f, filename="chart.png"))

    except Exception as e:
        await ctx.send("❌ Erreur lors de la génération du graphique.")
        print(f"[monchart] {e}")

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
async def anime_quiz(ctx):
    await ctx.send("🎮 Préparation du quiz...")

    anime = None
    for _ in range(10):
        page = random.randint(1, 500)
        query = f'''
        query {{
          Page(perPage: 1, page: {page}) {{
            media(type: ANIME, isAdult: false, sort: SCORE_DESC) {{
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

    # 📖 Description & traduction
    raw_description = anime.get("description", "Pas de description.").split(".")[0] + "."
    try:
        from deep_translator import GoogleTranslator
        description = GoogleTranslator(source='auto', target='fr').translate(raw_description)
    except:
        description = raw_description  # fallback

    # 🖼️ Embed
    embed = discord.Embed(
        title="🧠 Anime Quiz",
        description=f"**Description :**\n{description}\n\n*Tu as 20 secondes pour deviner l'anime.*",
        color=discord.Color.orange()
    )
    cover = anime.get("coverImage", {}).get("large")
    if cover:
        embed.set_image(url=cover)

    await ctx.send(embed=embed)

    correct_titles = title_variants(anime["title"])

    def check(m):
        return m.author == ctx.author and normalize(m.content) in correct_titles

    try:
        msg = await bot.wait_for("message", timeout=20.0, check=check)
        await ctx.send(f"✅ Bonne réponse, **{ctx.author.display_name}** !")

        # 🏆 Enregistrer le score
        scores = load_scores()
        user_id = str(ctx.author.id)
        scores[user_id] = scores.get(user_id, 0) + 1
        save_scores(scores)

    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Temps écoulé ! C’était **{anime['title']['romaji']}**.")


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
            "title": "📅 Épisodes & Planning",
            "fields": [
                ("`!next`", "Affiche le prochain épisode à sortir dans ta liste."),
                ("`!planning` / `!monplanning`", "Liste tous les épisodes à venir cette semaine."),
                ("`!prochains <genre>`", "Filtre les épisodes à venir selon un genre."),
                ("`!planningvisuel`", "Affiche un planning visuel de la semaine."),
            ]
        },
        {
            "title": "🎮 Quiz & Niveaux",
            "fields": [
                ("`!animequiz`", "Réponds à une question pour deviner l’anime."),
                ("`!animebattle @ami`", "Affronte un ami sur 3 questions anime."),
                ("`!quiztop`", "Classement des meilleurs joueurs au quiz."),
                ("`!myrank`", "Affiche ton niveau et XP obtenus."),
            ]
        },
        {
            "title": "🏆 Défis & Challenges",
            "fields": [
                ("`!anichallenge`", "Propose un anime à regarder et noter."),
                ("`!challenge complete <note>`", "Indique que tu as fini ton défi personnel."),
                ("`!weekly`", "Reçoit un défi hebdomadaire original."),
                ("`!weekly complete`", "Indique que tu as terminé ton défi de la semaine."),
            ]
        },
        {
            "title": "📊 Stats & Profils",
            "fields": [
                ("`!linkanilist <pseudo>`", "Lie ton compte AniList au bot."),
                ("`!unlink`", "Dissocie ton compte AniList."),
                ("`!mystats`", "Affiche ton profil AniList de façon stylisée."),
                ("`!stats <pseudo>`", "Affiche les stats d’un autre utilisateur."),
            ]
        },
        {
            "title": "📈 Comparaison & Genres",
            "fields": [
                ("`!duelstats @ami`", "Compare ton profil AniList avec un ami."),
                ("`!mychart`", "Affiche un graphique des genres que tu regardes."),
                ("`!classementgenre <genre>`", "Classement de ceux qui regardent le plus ce genre."),
            ]
        },
        {
            "title": "🔔 Notifications & Rappels",
            "fields": [
                ("`!reminder`", "Active ou désactive les rappels quotidiens."),
                ("`!setalert HH:MM`", "Choisis l’heure de ton rappel."),
                ("`!anitracker <titre>`", "Suis un anime pour recevoir les DM quand un épisode sort."),
                ("`!anitracker list` / `remove <titre>`", "Liste ou retire un anime suivi."),
            ]
        },
        {
            "title": "🛠️ Outils & Utilitaires",
            "fields": [
                ("`!uptime`", "Affiche depuis combien de temps le bot est actif."),
                ("`!setchannel`", "Définit ce salon comme canal de notifications (admin uniquement)."),
                ("`!topanime` / `!seasonal`", "Affiche les meilleurs animes de la saison."),
                ("`!search <titre>`", "Recherche un anime sur AniList."),
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
                if ep["title"] in titles:
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

    
    # Récupération du bon channel depuis la config
    config = get_config()
    channel_id = config.get("channel_id")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                await channel.send(f"🤖 AnimeBot a démarré et est prêt à traquer les sorties !")
            except:
                pass

    # ✅ Tâche 1 : résumé quotidien
    if not send_daily_summaries.is_running():
        send_daily_summaries.start()

    # ✅ Tâche 2 : alertes épisodes
    if not check_new_episodes.is_running():
        check_new_episodes.start()



# Lancer le bot
bot.run(DISCORD_TOKEN)

