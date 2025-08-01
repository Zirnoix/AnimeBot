"""
Core utilities and data management for the AnimeBot.

This module centralises all of the helper functions and global variables used
throughout the bot. It handles reading and writing JSON configuration
files, interfacing with the AniList GraphQL API, normalising strings for
comparison, maintaining a cache of title variants, and tracking scores,
levels, and user preferences. Splitting these functions into a single
module makes them easy to import from the various cogs without
duplicating code.

Much of the logic in this module has been extracted from the original
``main.py`` provided by the user. By moving it into a dedicated module
we avoid a monolithic file and allow each cog to focus on its own
commands.
"""

import json
import os
import re
import unicodedata
import random
import asyncio
from datetime import datetime, timedelta, timezone

import requests
import pytz
from babel.dates import format_datetime

###############################################################################
# Paths and configuration
#
# All JSON files used by the bot live in the ``data`` directory. If the
# directory does not exist it will be created on first access. Keeping
# these paths here in one place makes it easy to update where data is
# stored in the future (for example, moving to a different folder or
# migrating to a database).
###############################################################################

# Ensure the data directory exists
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

PREFERENCES_FILE = os.path.join(DATA_DIR, "preferences.json")
QUIZ_SCORES_FILE = os.path.join(DATA_DIR, "quiz_scores.json")
LINKED_FILE = os.path.join(DATA_DIR, "linked_users.json")
LEVELS_FILE = os.path.join(DATA_DIR, "quiz_levels.json")
TRACKER_FILE = os.path.join(DATA_DIR, "anitracker.json")
CHALLENGES_FILE = os.path.join(DATA_DIR, "challenges.json")
WEEKLY_FILE = os.path.join(DATA_DIR, "weekly.json")
USER_SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")
NOTIFIED_FILE = os.path.join(DATA_DIR, "notified.json")
LINKS_FILE = os.path.join(DATA_DIR, "user_links.json")
TITLE_CACHE_FILE = os.path.join(DATA_DIR, "title_cache.json")
WINNER_FILE = os.path.join(DATA_DIR, "quiz_winner.json")

# General configuration file for storing bot-wide settings such as
# the notification channel ID.
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# ID of the bot owner; used for privileged commands such as setchannel
OWNER_ID = 180389173985804288

# Load environment variables
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ANILIST_USERNAME = os.getenv("ANILIST_USERNAME", "Zirnoixdcoco")
TIMEZONE = pytz.timezone(os.getenv("BOT_TIMEZONE", "Europe/Paris"))

###############################################################################
# Configuration helpers
###############################################################################

def get_config() -> dict:
    """Return the bot configuration dictionary."""
    return load_json(CONFIG_FILE, {})

def save_config(data: dict) -> None:
    """Write the bot configuration to disk."""
    save_json(CONFIG_FILE, data)

###############################################################################
# JSON helper functions
#
# These functions read and write JSON with proper encoding and create empty
# files on demand. Using a thin wrapper ensures all JSON IO is uniform
# across the project.
###############################################################################

def load_json(path: str, default):
    """Load JSON data from ``path``. Return ``default`` if the file is missing.

    Args:
        path: The file path to load from.
        default: The value to return if the file does not exist or contains
            invalid JSON.

    Returns:
        The parsed JSON content or ``default``.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data) -> None:
    """Write ``data`` as JSON to ``path``.

    Args:
        path: Destination file path.
        data: Serializable object to save.
    """
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

###############################################################################
# Preferences and links management
###############################################################################

def load_preferences() -> dict:
    return load_json(PREFERENCES_FILE, {})

def save_preferences(data: dict) -> None:
    save_json(PREFERENCES_FILE, data)

def load_links() -> dict:
    return load_json(LINKED_FILE, {})

def save_links(data: dict) -> None:
    save_json(LINKED_FILE, data)

def get_user_anilist(user_id: int) -> str | None:
    """Return the AniList username linked to a Discord user ID, if any."""
    links = load_links()
    return links.get(str(user_id))

def load_user_settings() -> dict:
    """Load user-specific settings such as reminders and daily summaries."""
    return load_json(USER_SETTINGS_FILE, {})

def save_user_settings(settings: dict) -> None:
    """Persist user-specific settings."""
    save_json(USER_SETTINGS_FILE, settings)

###############################################################################
# Score and level management
###############################################################################

def load_scores() -> dict:
    return load_json(QUIZ_SCORES_FILE, {})

def save_scores(scores: dict) -> None:
    save_json(QUIZ_SCORES_FILE, scores)

def load_levels() -> dict:
    return load_json(LEVELS_FILE, {})

def save_levels(data: dict) -> None:
    save_json(LEVELS_FILE, data)

def add_xp(user_id: int, amount: int = 10) -> tuple[bool, int]:
    """Add XP to a user and handle level ups.

    Returns a tuple ``(leveled_up, new_level)``. XP thresholds scale
    linearly: level n requires (n+1)*100 XP.
    """
    uid = str(user_id)
    data = load_levels()
    if uid not in data:
        data[uid] = {'xp': 0, 'level': 0}
    data[uid]['xp'] += amount
    leveled_up = False
    while data[uid]['xp'] >= (data[uid]['level'] + 1) * 100:
        data[uid]['xp'] -= (data[uid]['level'] + 1) * 100
        data[uid]['level'] += 1
        leveled_up = True
    save_levels(data)
    return leveled_up, data[uid]['level']

def get_xp_bar(xp: int, total: int, length: int = 10) -> str:
    filled = int((xp / total) * length)
    empty = length - filled
    return "▰" * filled + "▱" * empty

###############################################################################
# Tracker and challenge storage
###############################################################################

def load_tracker() -> dict:
    return load_json(TRACKER_FILE, {})

def save_tracker(data: dict) -> None:
    save_json(TRACKER_FILE, data)

def load_weekly() -> dict:
    return load_json(WEEKLY_FILE, {})

def save_weekly(data: dict) -> None:
    save_json(WEEKLY_FILE, data)

def load_challenges() -> dict:
    return load_json(CHALLENGES_FILE, {})

def save_challenges(data: dict) -> None:
    save_json(CHALLENGES_FILE, data)

###############################################################################
# Title normalisation and caching
#
# To compare user input against anime titles, we normalise strings by
# removing accents, punctuation and extra spaces. We also maintain a
# cache of title variants (romaji, english, native and manually defined
# aliases) so that common abbreviations are recognised during quizzes.
###############################################################################

def normalize(text: str | None) -> str:
    if not text:
        return ""
    # Remove accents
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    # Keep only alphanumeric and spaces
    return ''.join(e for e in text.lower() if e.isalnum() or e.isspace()).strip()

def load_title_cache() -> dict:
    return load_json(TITLE_CACHE_FILE, {})

def save_title_cache(cache: dict) -> None:
    save_json(TITLE_CACHE_FILE, cache)

def title_variants(title_data: dict) -> set[str]:
    """Return a set of plausible input variants for an anime title.

    This includes the romaji, english and native titles, cleaned up and
    abbreviated, plus a selection of common aliases for popular series.
    """
    titles: set[str] = set()
    # Basic keys
    for key in ['romaji', 'english', 'native']:
        t = title_data.get(key)
        if not t:
            continue
        base = normalize(t)
        # Remove common words like season indicators
        clean = re.sub(r"(saison|season|s\d|2nd|second|3rd|third|final|part \d+|ver\d+|[^\w\s])", "", base, flags=re.IGNORECASE).strip()
        titles.add(base)
        titles.add(clean)
        for word in clean.split():
            if len(word) >= 4:
                titles.add(word)
    # Manual aliases for popular shows
    aliases: dict[str, set[str]] = {
        "one piece": {"op", "onepiece", "op film", "stampede"},
        "hajime no ippo": {"ippo", "hni", "champion road", "hajime"},
        "attack on titan": {"snk", "aot", "shingeki"},
        "my hero academia": {"mha", "boku no hero academia", "hero academia"},
        "sword art online": {"sao"},
        "demon slayer": {"kimetsu no yaiba", "kny"},
        "jujutsu kaisen": {"jjk"},
        "hunter x hunter": {"hxh"},
        "tokyo ghoul": {"tg"},
        "nier automata": {"nier"},
        "bleach": {"tybw"},
        "mob psycho 100": {"mob"},
        "one punch man": {"opm"},
        "naruto": {"shippuden"},
        "black clover": {"blackclover"},
        "dr stone": {"dr. stone"},
        "re zero": {"rezero"},
        "tokyo revengers": {"revengers", "tokrev"},
        "chainsaw man": {"csm"},
        "fire force": {"enka"},
        "fairy tail": {"fairytail", "ft"},
        "blue lock": {"bluelock", "bl"},
        "spy x family": {"spyxfamily", "spy family"},
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
        "frieren": {"sousou no frieren"},
        "steins gate": {"sg", "steins"},
        "meitantei conan": {"detective conan", "conan"},
        "no game no life": {"ngnl"},
        "future diary": {"mirai nikki"},
        "parasyte": {"kiseijuu"},
        "rent a girlfriend": {"kanokari"},
        "your name": {"kimi no na wa", "yourname"},
        "a silent voice": {"koe no katachi"},
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
        "horimiya": set(),
        "another": set(),
        "angel beats": set(),
        "gintama": {"gintoki"},
        "overlord": set(),
        "eromanga sensei": {"eromanga"},
        "highschool dxd": {"dxd"},
        "tokyo avengers": {"tokrev"},
        "konosuba": set(),
        "naruto shippuden": {"naruto", "shippuden"},
    }
    base_all = [normalize(title_data.get(k, "")) for k in ['romaji', 'english', 'native']]
    for b in base_all:
        for key, values in aliases.items():
            if key in b:
                titles.update(values)
    return {normalize(t) for t in titles if len(t) > 1}

def update_title_cache() -> None:
    """Fetch the current user's list from AniList and update the title cache.

    The cache maps normalised title variants to the canonical romaji title.
    It reduces the number of API calls required during quiz lookups.
    """
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
        all_titles: list[dict] = []
        for lst in entries:
            for entry in lst["entries"]:
                titles = entry["media"]["title"]
                all_titles.append(titles)
        cache: dict[str, list[str]] = {}
        for t in all_titles:
            variants = title_variants(t)
            for v in variants:
                cache.setdefault(v, []).append(t["romaji"])
        save_title_cache(cache)
        print(f"[CACHE ✅] {len(cache)} titres ajoutés au cache.")
    except Exception as e:
        print(f"[CACHE ❌] Erreur lors de la mise à jour : {e}")

###############################################################################
# AniList API wrapper
###############################################################################

def query_anilist(query: str, variables: dict | None = None) -> dict | None:
    """Send a GraphQL query to AniList and return the JSON response.

    Returns None on error.
    """
    try:
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables or {}},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return None

def get_upcoming_episodes(username: str) -> list[dict]:
    """Return a list of upcoming episodes for the given AniList user.

    Each entry contains keys: id, title, episode, airingAt (unix timestamp),
    genres, image (URL). Entries without a nextAiringEpisode are skipped.
    """
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
    try:
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables}
        )
        response.raise_for_status()
        data = response.json()
        entries: list[dict] = []
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
        return entries
    except Exception:
        return []

###############################################################################
# Genre helpers
###############################################################################

JOURS_FR = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi", "Thursday": "Jeudi",
    "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"
}

def genre_emoji(genres: list[str]) -> str:
    emojis = {
        "Action": "⚔️", "Comedy": "😂", "Drama": "🎭", "Fantasy": "🧙‍♂️",
        "Romance": "💕", "Sci-Fi": "🚀", "Horror": "👻", "Mystery": "🕵️",
        "Sports": "🏅", "Music": "🎵", "Slice of Life": "🍃"
    }
    for g in genres:
        if g in emojis:
            return emojis[g]
    return "🎬"

def build_embed(ep: dict, dt: datetime) -> 'discord.Embed':
    """Construct a simple embed announcing the release of an episode.

    Note: this function is typed as returning a Discord Embed but the
    dependency is optional; cogs import and use it when they have access to
    discord.py. Keeping it here avoids a circular import.
    """
    import discord  # imported locally to avoid optional import at module level
    emoji = genre_emoji(ep.get("genres", []))
    embed = discord.Embed(
        title=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
        description=f"📅 {JOURS_FR[dt.strftime('%A')]} {dt.strftime('%d/%m')} à {dt.strftime('%H:%M')}",
        color=discord.Color.blurple()
    )
    if ep.get("image"):
        embed.set_thumbnail(url=ep["image"])
    return embed

###############################################################################
# Miscellaneous helpers
###############################################################################

def format_date_fr(dt: datetime, pattern: str = "EEEE d MMMM") -> str:
    """Format a datetime in French locale."""
    return format_datetime(dt, pattern, locale='fr_FR').capitalize()

def get_title_for_level(level: int) -> str:
    """Return a fun title based on the user's level."""
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
        (100, "🧠 Le Grand Archiviste Suprême 🏆"),
    ]
    result = "🌱 Débutant"
    for lvl, name in titles:
        if level >= lvl:
            result = name
        else:
            break
    return result
