# AnimeBot — Version finale avec !setchannel, préférences, alertes, !prochains stylisé
import discord
from discord.ext import commands, tasks
import requests
import json
import asyncio
import os
import pytz
from datetime import datetime, timedelta

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

OWNER_ID = None

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
async def prochains(ctx, mode: str = "10"):
    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    if not episodes:
        await ctx.send("Aucun épisode à venir.")
        return

    try:
        if mode.lower() in ["all", "tout"]:
            max_items = 100
        else:
            max_items = min(100, int(mode))
    except:
        max_items = 10

    episodes = sorted(episodes, key=lambda e: e["airingAt"])[:max_items]
    pages = []
    group_size = 5

    for i in range(0, len(episodes), group_size):
        group = episodes[i:i+group_size]
        embed = discord.Embed(
            title=f"📅 Prochains épisodes — Page {len(pages)+1}",
            description="Voici les épisodes à venir :",
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
            pages[self.index].title = f"📅 Prochains épisodes — Page {self.index+1}"
            await i.response.edit_message(embed=pages[self.index], view=self)
        @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
        async def next(self, i, b):
            self.index = min(len(pages)-1, self.index + 1)
            pages[self.index].title = f"📅 Prochains épisodes — Page {self.index+1}"
            await i.response.edit_message(embed=pages[self.index], view=self)

    pages[0].title = f"📅 Prochains épisodes — Page 1"
    await ctx.send(embed=pages[0], view=Paginator())




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
        await ctx.send("Aucun épisode prévu.")
        return
    group = {}
    for ep in episodes:
        dt = datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE)
        day = jours_fr[dt.strftime("%A")]
        group.setdefault(day, []).append((ep, dt))
    ordered_days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    for jour in ordered_days:
        if jour not in group:
            continue
        liste = group[jour]
        embed = discord.Embed(title=f"🗓️ {jour}", color=discord.Color.orange())
        for ep, dt in liste:
            emoji = genre_emoji(ep["genres"])
            embed.add_field(name=f"{emoji} {ep['title']} — Ép {ep['episode']}", value=dt.strftime("%H:%M"), inline=False)
        await ctx.send(embed=embed)

@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="📘 Commandes disponibles",
        description="Voici toutes les commandes que tu peux utiliser avec AnimeBot :",
        color=discord.Color.blue()
    )

    embed.add_field(name="📅 !prochains", value="Liste paginée des épisodes à venir", inline=False)
    embed.add_field(name="⏭️ !next", value="Affiche le prochain épisode à sortir", inline=False)
    embed.add_field(name="📆 !aujourdhui", value="Affiche les épisodes qui sortent aujourd’hui", inline=False)
    embed.add_field(name="🗓️ !planning", value="Planning complet de la semaine (trié par jour)", inline=False)

    embed.add_field(name="🔔 !setalert <minutes>", value="Change ton délai de rappel (ex: 15min avant la sortie)", inline=False)
    embed.add_field(name="📬 !journalier [on/off]", value="Active ou désactive le résumé privé chaque matin", inline=False)
    embed.add_field(name="📩 !reminder [on/off]", value="Active ou désactive les rappels privés pour chaque sortie", inline=False)

    embed.add_field(name="📌 !setchannel", value="Définit le canal où les alertes s’affichent (réservé à toi)", inline=False)

    embed.set_footer(text="AnimeBot développé avec ❤️")
    await ctx.send(embed=embed)


    
@bot.command(name="setalert")
async def setalert(ctx, minutes: int):
    uid = str(ctx.author.id)
    user_settings.setdefault(uid, {})
    user_settings[uid]["alert_minutes"] = minutes
    save_json(USER_SETTINGS_FILE, user_settings)
    await ctx.send(f"⏱️ Délai de rappel personnalisé défini à **{minutes} minutes** avant la sortie.")
    
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
    print(f"[✅ BOT DÉMARRÉ] AnimeBot actif depuis le {now}")
    
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if channel:
        await channel.send(f"🤖 AnimeBot a redémarré ({now}) et est prêt à traquer les sorties !")

    bot.loop.create_task(check_new_episodes())
    bot.loop.create_task(send_daily_summary())

@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} est connecté.")

    # Tâches de fond
    if not hasattr(bot, "daily_summary_task"):
        bot.daily_summary_task = asyncio.create_task(send_daily_summaries())

    if not hasattr(bot, "episode_alert_task"):
        bot.episode_alert_task = asyncio.create_task(check_new_episodes())

    try:
        channel = bot.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            await channel.send("🤖 AnimeBot prêt à traquer les sorties d’épisodes !")
    except:
        pass


async def send_daily_summaries():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now(TIMEZONE)
        if now.hour == 7 and now.minute < 5:  # entre 7h00 et 7h04
            episodes = get_upcoming_episodes(ANILIST_USERNAME)
            for uid, settings in user_settings.items():
                if not settings.get("daily_summary", False):
                    continue
                user = await bot.fetch_user(int(uid))
                if user is None:
                    continue
                today_eps = []
                for ep in episodes:
                    dt = datetime.fromtimestamp(ep["airingAt"], tz=pytz.utc).astimezone(TIMEZONE)
                    if dt.date() == now.date():
                        today_eps.append((ep, dt))

                if not today_eps:
                    continue

                embed = discord.Embed(
                    title="📆 Épisodes du jour",
                    description=f"Voici ce qui sort aujourd’hui ({now.strftime('%d/%m/%Y')}) :",
                    color=discord.Color.green()
                )
                for ep, dt in today_eps:
                    emoji = genre_emoji(ep["genres"])
                    embed.add_field(
                        name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                        value=f"🕒 {dt.strftime('%H:%M')}",
                        inline=False
                    )
                try:
                    await user.send(embed=embed)
                except discord.Forbidden:
                    print(f"❌ Impossible d’envoyer le résumé quotidien à {user.name}")

        await asyncio.sleep(300)


# Lancer le bot
bot.run(DISCORD_TOKEN)

