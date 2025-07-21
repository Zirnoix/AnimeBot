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
PREFERENCES_FILE = "preferences.json"

QUIZ_SCORES_FILE = "quiz_scores.json"

def load_scores():
    if not os.path.exists(QUIZ_SCORES_FILE):
        return {}
    with open(QUIZ_SCORES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_scores(scores):
    with open(QUIZ_SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2, ensure_ascii=False)

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

print(f"BOT ACTIVÉ — ID : {bot.user.id}")

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
USER_SETTINGS_FILE = "user_settings.json"
NOTIFIED_FILE = "notified.json"

LINKS_FILE = "user_links.json"

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
    query = '''
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME) {
        lists {
          entries {
            media {
              id
              title { romaji }
              coverImage { large }
              genres
              nextAiringEpisode {
                airingAt
                episode
              }
            }
          }
        }
      }
    }
    '''
    response = requests.post("https://graphql.anilist.co", json={'query': query, 'variables': {'name': username}})
    try:
        data = response.json()
    except:
        return []
    if not data.get("data") or not data["data"].get("MediaListCollection"):
        return []
    result = []
    for group in data["data"]["MediaListCollection"]["lists"]:
        for entry in group["entries"]:
            media = entry["media"]
            ep = media.get("nextAiringEpisode")
            if ep:
                result.append({
                    "id": media["id"],
                    "title": media["title"]["romaji"],
                    "episode": ep["episode"],
                    "airingAt": ep["airingAt"],
                    "image": media["coverImage"]["large"],
                    "genres": media["genres"]
                })
    return result

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

@bot.command(name="linkanilist")
async def link_anilist(ctx, username: str):
    user_links[ctx.author.id] = username
    save_user_links()
    await ctx.send(f"✅ Ton profil Anilist a bien été lié à **{username}**.")

@bot.command(name="quiztop")
async def quiztop(ctx):
    scores = load_scores()
    if not scores:
        await ctx.send("🏆 Aucun score enregistré pour l’instant.")
        return

    leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
    desc = ""
    for i, (uid, score) in enumerate(leaderboard, 1):
        user = await bot.fetch_user(int(uid))
        desc += f"{i}. **{user.display_name}** – {score} pts\n"

    embed = discord.Embed(
        title="🏆 Classement Anime Quiz",
        description=desc,
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

@bot.command(name="animebattle")
async def anime_battle(ctx, opponent: discord.Member):
    if opponent.bot:
        await ctx.send("🤖 Tu ne peux pas défier un bot.")
        return

    await ctx.send(f"🎮 Duel entre **{ctx.author.display_name}** et **{opponent.display_name}** !")

    players = [ctx.author, opponent]
    scores = {p.id: 0 for p in players}

    for round_num in range(1, 4):
        await ctx.send(f"❓ Question {round_num}/3...")

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
            await ctx.send("❌ Erreur lors de la récupération de l’anime.")
            return

        desc = anime["description"].split(".")[0] + "."
        embed = discord.Embed(
            title="🧠 Devine l’anime",
            description=f"**Description :**\n{desc}\n\n*15 secondes pour répondre.*",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

        correct_titles = title_variants(anime["title"])

        def check(m):
            return m.author in players and normalize(m.content) in correct_titles

        try:
            msg = await bot.wait_for("message", timeout=15.0, check=check)
            scores[msg.author.id] += 1
            await ctx.send(f"✅ Bonne réponse par **{msg.author.display_name}** !")
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Personne n’a trouvé. C’était **{anime['title']['romaji']}**")

    p1, p2 = players
    s1, s2 = scores[p1.id], scores[p2.id]
    if s1 == s2:
        result = "🤝 Égalité parfaite !"
    else:
        winner = p1 if s1 > s2 else p2
        result = f"🏆 Victoire de **{winner.display_name}** ({s1} - {s2})"

    await ctx.send(result)

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
    if ctx.author.id in user_links:
        del user_links[ctx.author.id]
        save_user_links()
        await ctx.send("🗑️ Ton lien Anilist a été supprimé.")
    else:
        await ctx.send("❌ Aucun lien trouvé pour ton compte.")


@bot.command(name="mystats")
async def mystats(ctx):
    username = user_links.get(ctx.author.id)
    if not username:
        await ctx.send("❌ Tu n'as pas encore lié ton compte Anilist. Utilise `!linkanilist <pseudo>`.")
        return
    await stats(ctx, username=username)  # Appelle la commande `!stats`

# Commande pour voir les stats
@bot.command(name="stats")
async def stats(ctx, username: str):
    import requests
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from io import BytesIO

    query = '''
    query ($name: String) {
      User(name: $name) {
        name
        avatar {
          large
        }
        bannerImage
        statistics {
          anime {
            count
            minutesWatched
            meanScore
            genres {
              genre
              count
            }
          }
        }
        siteUrl
      }
    }
    '''
    variables = {"name": username}
    url = "https://graphql.anilist.co"

    try:
        response = requests.post(url, json={"query": query, "variables": variables})
        response.raise_for_status()
        json_data = response.json()
        user_data = json_data.get("data", {}).get("User", None)
    except Exception:
        await ctx.send("🚫 Erreur lors de la récupération des données Anilist.")
        return

    if not user_data:
        await ctx.send(f"❌ Le pseudo **{username}** est introuvable sur Anilist.")
        return

    stats = user_data["statistics"]["anime"]
    genres = stats["genres"]
    favorite_genre = sorted(genres, key=lambda g: g["count"], reverse=True)[0]["genre"] if genres else "N/A"
    days = round(stats["minutesWatched"] / 1440, 1)

    avatar = Image.open(BytesIO(requests.get(user_data["avatar"]["large"]).content)).resize((128, 128)).convert("RGBA")
    banner_url = user_data["bannerImage"] or "https://s4.anilist.co/file/anilistcdn/media/anime/banner/101922-oJxzcFvSTFZg.jpg"
    banner = Image.open(BytesIO(requests.get(banner_url).content)).resize((800, 300)).convert("RGBA")

    # Flou et overlay foncé
    blur = banner.filter(ImageFilter.GaussianBlur(3))
    overlay = Image.new("RGBA", blur.size, (0, 0, 0, 180))
    card = Image.alpha_composite(blur, overlay)

    card.paste(avatar, (30, 86), avatar)
    draw = ImageDraw.Draw(card)

    # Polices
    font_title = ImageFont.truetype("fonts/DejaVuSans-Bold.ttf", 24)
    font_text = ImageFont.truetype("fonts/DejaVuSans.ttf", 18)

    # Contenu stylisé
    draw.text((180, 30), f"👤 {user_data['name']}", font=font_title, fill="white")
    draw.text((180, 80), f"🎬 Animés vus : {stats['count']}", font=font_text, fill="white")
    draw.text((180, 110), f"🕒 Temps total : {days} jours", font=font_text, fill="white")
    draw.text((180, 140), f"⭐ Score moyen : {round(stats['meanScore'], 1)}", font=font_text, fill="white")
    draw.text((180, 170), f"💖 Genre préféré : {favorite_genre}", font=font_text, fill="white")
    draw.text((180, 220), f"🔗 {user_data['siteUrl']}", font=font_text, fill="white")

    # Sauvegarde
    image_path = f"/tmp/{username}_profile.png"
    card.save(image_path)

    with open(image_path, "rb") as f:
        await ctx.send(file=discord.File(f, filename=f"{username}_stats.png"))


# Commandes supplémentaires
@bot.command(name="next")
async def next_episode(ctx):
    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    if not episodes:
        await ctx.send("Aucun épisode à venir.")
        return
    ep = min(episodes, key=lambda e: e["airingAt"])
    dt = datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE)
    await ctx.send(embed=build_embed(ep, dt))

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
              description(asHtml: false)
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

    # Description
    raw_description = anime.get("description", "Pas de description.").split(".")[0] + "."
    try:
        from deep_translator import GoogleTranslator
        description = GoogleTranslator(source='auto', target='fr').translate(raw_description)
    except:
        description = raw_description  # fallback si la traduction échoue

    embed = discord.Embed(
        title="🧠 Anime Quiz",
        description=f"**Description :**\n{description}\n\n*Tu as 20 secondes pour deviner l'anime.*",
        color=discord.Color.orange()
    )

    # Ajoute image
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

    
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="📖 Commandes disponibles",
        description="Voici toutes les commandes d'AnimeBot",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="🗓️ Prochains épisodes",
        value=(
            "`!prochains` – Affiche les 10 épisodes à venir\n"
            "`!prochains all` ou `!prochains 25` – Jusqu'à 100 épisodes\n"
            "`!prochains action` – Filtrer par genre\n"
            "`!prochains romance 20` – Filtrer genre + nombre"
        ),
        inline=False
    )

    embed.add_field(
        name="📅 Planning & résumés",
        value=(
            "`!planning` – Planning des sorties de la semaine\n"
            "`!journalier` – Animes du jour uniquement\n"
            "`!aujourdhui` – Affiche les épisodes diffusés aujourd’hui\n"
            "`!next` – Le prochain épisode à sortir"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Mini-jeux",
        value=(
            "`!animequiz` – Devine l’anime à partir d’une description\n"
            "`!quiztop` – Classement des meilleurs joueurs du quiz"
        ),
        inline=False
    )

    embed.add_field(
        name="🔍 Recherche & recommandations",
        value=(
            "`!search <titre>` – Recherche un anime par nom\n"
            "`!suggest` – Recommande un anime de ta liste\n"
            "`!suggest <genre>` – Recommande un anime par genre\n"
            "`!topanime` – Top 10 des animés les mieux notés\n"
            "`!seasonal` – Animes de la saison en cours"
        ),
        inline=False
    )

    embed.add_field(
        name="🎯 Personnalisation",
        value=(
            "`!reminder on/off` – Activer ou désactiver les rappels DM\n"
            "`!setalert <heure>` – Heure du résumé (ex: `!setalert 09:00`)"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Statistiques & profil",
        value=(
            "`!stats <pseudo>` – Affiche une carte de profil Anilist stylisée\n"
            "`!linkanilist <pseudo>` – Lie ton compte Discord à Anilist\n"
            "`!mystats` – Ton profil Anilist automatiquement\n"
            "`!unlink` – Supprime ton lien avec Anilist"
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ Utilitaire",
        value="`!uptime` – Depuis combien de temps le bot est actif",
        inline=False
    )

    embed.set_footer(text="AnimeBot – connecté à ton AniList ❤️")

    await ctx.send(embed=embed)
    
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
            
@bot.event
async def on_ready():
    now = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
    print(f"[✅ BOT DÉMARRÉ] {bot.user.name} actif depuis le {now}")

    # Récupération du bon channel depuis la config
    config = get_config()
    channel_id = config.get("channel_id")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                await channel.send(f"🤖 AnimeBot a redémarré ({now}) et est prêt à traquer les sorties !")
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

