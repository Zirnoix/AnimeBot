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
from PIL import Image, ImageDraw, ImageFont  # New: for image generation
import io

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
MINI_SCORES_FILE = os.path.join(DATA_DIR, "mini_scores.json")

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
# Mini-games scoring
###############################################################################

def load_mini_scores() -> dict:
    """Load the mini-game scores per user and game name."""
    return load_json(MINI_SCORES_FILE, {})

def save_mini_scores(data: dict) -> None:
    save_json(MINI_SCORES_FILE, data)

def add_mini_score(user_id: int, game: str, amount: int = 1) -> None:
    """Increment mini-game score for a specific game and user."""
    data = load_mini_scores()
    uid = str(user_id)
    data.setdefault(uid, {})
    data[uid][game] = data[uid].get(game, 0) + amount
    save_mini_scores(data)

def get_mini_scores(user_id: int) -> dict:
    """Return the mini-game score dictionary for the given user ID."""
    return load_mini_scores().get(str(user_id), {})

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

###############################################################################
# Image generation helpers
#
# These helpers create visuals for certain commands such as ``!next``. They
# download the cover image, compose a stylised card with the episode
# information, and return a byte buffer that can be sent as an attachment
# in Discord. If required fonts are unavailable, they gracefully fall back
# to the default Pillow font.
###############################################################################

def generate_next_image(ep: dict, dt: datetime, tagline: str = "Prochain épisode") -> io.BytesIO:
    """Generate a stylised image announcing the next episode.

    Args:
        ep: A dict representing the episode with keys ``title``, ``episode`` and ``image``.
        dt: A timezone-aware datetime of the airing time.
        tagline: A short string displayed at the bottom of the card.

    Returns:
        A BytesIO object containing the JPEG image data.
    """
    # Image dimensions
    width, height = 900, 500
    cover_width = int(width * 0.45)
    # Create background
    card = Image.new("RGB", (width, height), color=(20, 20, 20))
    # Fetch cover image
    try:
        response = requests.get(ep.get("image"), timeout=10)
        cover = Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception:
        # Fallback to solid color if the image cannot be fetched
        cover = Image.new("RGB", (cover_width, height), color=(50, 50, 50))
    # Resize and crop cover to fit
    cover_ratio = cover.width / cover.height
    target_ratio = cover_width / height
    if cover_ratio > target_ratio:
        # Cover is wider, crop horizontally
        new_height = height
        new_width = int(height * cover_ratio)
        resized = cover.resize((new_width, new_height))
        left = (new_width - cover_width) // 2
        cover = resized.crop((left, 0, left + cover_width, height))
    else:
        # Cover is taller, crop vertically
        new_width = cover_width
        new_height = int(cover_width / cover_ratio)
        resized = cover.resize((new_width, new_height))
        top = (new_height - height) // 2
        cover = resized.crop((0, top, cover_width, top + height))
    # Paste cover onto card
    card.paste(cover, (0, 0))
    # Dark overlay on right side
    overlay = Image.new("RGBA", (width - cover_width, height), (0, 0, 0, 180))
    card.paste(overlay, (cover_width, 0), overlay)
    # Prepare drawing context
    draw = ImageDraw.Draw(card)
    # Load fonts
    def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()
    font_title = load_font("Bold", 34)
    font_sub = load_font("Regular", 24)
    font_small = load_font("Regular", 20)
    # Starting positions
    x0 = cover_width + 30
    y = 30
    # Draw title (wrapped if too long)
    title = ep.get("title", "Titre inconnu")
    # Simple wrapping: split by words to fit within the right panel width
    max_width = width - cover_width - 40
    words = title.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        w, _ = draw.textsize(test, font=font_title)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines:
        draw.text((x0, y), line, font=font_title, fill=(255, 255, 255))
        y += font_title.getsize(line)[1] + 2
    y += 10
    # Episode number
    ep_num = ep.get("episode")
    draw.text((x0, y), f"Épisode {ep_num}", font=font_sub, fill=(255, 215, 0))
    y += font_sub.getsize("Épisode 00")[1] + 10
    # Airing date and time
    day_fr = JOURS_FR.get(dt.strftime("%A"), dt.strftime("%A"))
    date_str = dt.strftime("%d %b %Y • %H:%M")
    draw.text((x0, y), f"{day_fr} {date_str}", font=font_sub, fill=(200, 200, 200))
    # Tagline at bottom
    tagline_w, tagline_h = draw.textsize(tagline, font=font_small)
    draw.text((x0, height - tagline_h - 30), tagline, font=font_small, fill=(150, 150, 150))
    # Export to BytesIO
    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


def generate_stats_card(
    user_name: str,
    avatar_url: str | None,
    anime_count: int,
    days_watched: float,
    mean_score: float,
    fav_genre: str,
) -> io.BytesIO:
    """Generate a stylised card displaying user statistics.

    Args:
        user_name: Display name of the user.
        avatar_url: URL of the user's Discord avatar (PNG or JPG). Can be None.
        anime_count: Number of anime watched.
        days_watched: Total days watched.
        mean_score: Mean score.
        fav_genre: Favourite genre.

    Returns:
        A BytesIO object containing the JPEG image.
    """
    width, height = 900, 500
    left_width = 220
    card = Image.new("RGB", (width, height), color=(20, 20, 20))
    # Fetch avatar or use placeholder
    def fetch_avatar(url: str) -> Image.Image:
        try:
            resp = requests.get(url, timeout=10)
            img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            return img
        except Exception:
            return Image.new("RGBA", (left_width, left_width), color=(80, 80, 80, 255))
    if avatar_url:
        avatar = fetch_avatar(avatar_url)
    else:
        avatar = Image.new("RGBA", (left_width, left_width), color=(80, 80, 80, 255))
    # Resize and crop avatar to square
    size = left_width - 40
    avatar_ratio = avatar.width / avatar.height
    if avatar_ratio > 1:
        # wider
        new_height = size
        new_width = int(new_height * avatar_ratio)
        tmp = avatar.resize((new_width, new_height))
        left = (new_width - size) // 2
        avatar = tmp.crop((left, 0, left + size, size))
    else:
        # taller or equal
        new_width = size
        new_height = int(new_width / avatar_ratio)
        tmp = avatar.resize((new_width, new_height))
        top = (new_height - size) // 2
        avatar = tmp.crop((0, top, size, top + size))
    # Make circular
    mask = Image.new("L", (size, size), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, size, size), fill=255)
    avatar.putalpha(mask)
    # Paste avatar on card
    avatar_pos = (int((left_width - size) / 2), 40)
    card.paste(avatar, avatar_pos, avatar)
    # Draw username
    draw = ImageDraw.Draw(card)
    # Load fonts
    def load_font_s(name: str, size: int) -> ImageFont.FreeTypeFont:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()
    font_name = load_font_s("Bold", 28)
    font_label = load_font_s("Regular", 22)
    font_value = load_font_s("Bold", 26)
    # Write user name centered under avatar
    name_text = user_name
    w, h = draw.textsize(name_text, font=font_name)
    draw.text(((left_width - w) / 2, avatar_pos[1] + size + 10), name_text, font=font_name, fill=(255, 255, 255))
    # Right panel overlay
    overlay = Image.new("RGBA", (width - left_width, height), (0, 0, 0, 180))
    card.paste(overlay, (left_width, 0), overlay)
    # Stats positions
    x0 = left_width + 40
    y_start = 80
    spacing = 60
    # Draw labels and values
    stats = [
        ("Animés vus", str(anime_count), (255, 215, 0)),
        ("Temps total", f"{days_watched:.1f} jours", (100, 200, 255)),
        ("Score moyen", f"{mean_score:.1f}", (255, 175, 200)),
        ("Genre préféré", fav_genre, (170, 255, 170)),
    ]
    for idx, (label, value, colour) in enumerate(stats):
        y = y_start + idx * spacing
        draw.text((x0, y), label, font=font_label, fill=(200, 200, 200))
        draw.text((x0 + 250, y), value, font=font_value, fill=colour)
    # Title at top of right panel
    title_font = load_font_s("Bold", 32)
    title = "Statistiques AniList"
    draw.text((x0, 20), title, font=title_font, fill=(255, 255, 255))
    # Export
    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


def generate_genre_chart(top_genres: list[tuple[str, int, int]], title: str = "Genres préférés") -> io.BytesIO:
    """Create a horizontal bar chart image for genres.

    Args:
        top_genres: A list of tuples ``(genre, count, percent)`` sorted by decreasing count.
        title: The title displayed at the top of the chart.

    Returns:
        A BytesIO object with the chart image in JPEG format.
    """
    width, height = 900, 500
    margin_x = 180
    top_margin = 80
    bar_height = 40
    spacing = 20
    # Compute chart height
    chart_height = len(top_genres) * (bar_height + spacing) - spacing
    total_height = max(height, top_margin + chart_height + 60)
    img = Image.new("RGB", (width, total_height), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)
    # Title
    def load_font_chart(size: int) -> ImageFont.FreeTypeFont:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()
    font_title = load_font_chart(32)
    font_label = load_font_chart(24)
    font_value = load_font_chart(22)
    draw.text((margin_x, 20), title, font=font_title, fill=(255, 255, 255))
    # Define colors for bars
    colors = [
        (255, 99, 132),  # red
        (54, 162, 235),  # blue
        (255, 206, 86),  # yellow
        (75, 192, 192),  # teal
        (153, 102, 255), # purple
        (255, 159, 64),  # orange
    ]
    # Max bar width
    max_width = width - margin_x - 150
    # Draw bars
    for idx, (genre, count, percent) in enumerate(top_genres):
        y = top_margin + idx * (bar_height + spacing)
        bar_w = int((percent / 100) * max_width)
        color = colors[idx % len(colors)]
        # Bar rectangle
        draw.rectangle([
            (margin_x, y),
            (margin_x + bar_w, y + bar_height)
        ], fill=color)
        # Label
        draw.text((30, y + bar_height / 4), genre, font=font_label, fill=(200, 200, 200))
        # Percentage text
        percent_text = f"{percent}%"
        draw.text((margin_x + bar_w + 10, y + bar_height / 4), percent_text, font=font_value, fill=(230, 230, 230))
    # Export
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


def generate_profile_card(
    user_name: str,
    avatar_url: str | None,
    level: int,
    xp: int,
    next_xp: int,
    quiz_score: int,
    mini_scores: dict[str, int],
) -> io.BytesIO:
    """Generate a profile card summarising XP, quiz and mini‑game scores.

    Args:
        user_name: Display name.
        avatar_url: URL to the user's Discord avatar.
        level: Current level of the user.
        xp: Current XP towards next level.
        next_xp: XP threshold for the next level.
        quiz_score: Total quiz score.
        mini_scores: Dict mapping mini-game names to counts.

    Returns:
        BytesIO containing a JPEG image.
    """
    width, height = 950, 550
    left_width = 220
    img = Image.new("RGB", (width, height), color=(20, 20, 20))
    # Fetch avatar
    def fetch_avatar(url: str) -> Image.Image:
        try:
            resp = requests.get(url, timeout=10)
            return Image.open(io.BytesIO(resp.content)).convert("RGBA")
        except Exception:
            return Image.new("RGBA", (left_width, left_width), color=(80, 80, 80, 255))
    if avatar_url:
        avatar = fetch_avatar(avatar_url)
    else:
        avatar = Image.new("RGBA", (left_width, left_width), color=(80, 80, 80, 255))
    # Crop and resize avatar to circle
    size = left_width - 40
    # Resize avatar preserving aspect ratio
    ratio = avatar.width / avatar.height
    if ratio > 1:
        tmp = avatar.resize((int(size * ratio), size))
        left = (tmp.width - size) // 2
        avatar = tmp.crop((left, 0, left + size, size))
    else:
        tmp = avatar.resize((size, int(size / ratio)))
        top = (tmp.height - size) // 2
        avatar = tmp.crop((0, top, size, top + size))
    # Make circular mask
    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse((0, 0, size, size), fill=255)
    avatar.putalpha(mask)
    img.paste(avatar, (int((left_width - size) / 2), 40), avatar)
    draw = ImageDraw.Draw(img)
    # Load fonts
    def load_font_prof(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        files = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for path in files:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()
    font_title = load_font_prof(32, bold=True)
    font_name = load_font_prof(28, bold=True)
    font_label = load_font_prof(22, bold=False)
    font_value = load_font_prof(24, bold=True)
    # Draw user name under avatar
    name_text = user_name
    w, h = draw.textsize(name_text, font=font_name)
    draw.text(((left_width - w) / 2, 40 + size + 10), name_text, font=font_name, fill=(255, 255, 255))
    # Right panel overlay
    overlay = Image.new("RGBA", (width - left_width, height), (0, 0, 0, 180))
    img.paste(overlay, (left_width, 0), overlay)
    # Title
    draw.text((left_width + 30, 20), "🎴 Carte Membre", font=font_title, fill=(255, 255, 255))
    # Level & XP bar
    bar_x = left_width + 30
    bar_y = 80
    bar_width = 450
    bar_height = 20
    # Background bar
    draw.rectangle([(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)], fill=(60, 60, 60))
    # Filled bar proportional to XP
    ratio_xp = min(max(xp / max(next_xp, 1), 0), 1)
    filled_w = int(bar_width * ratio_xp)
    draw.rectangle([(bar_x, bar_y), (bar_x + filled_w, bar_y + bar_height)], fill=(100, 200, 255))
    # XP text
    draw.text((bar_x + bar_width + 10, bar_y - 4), f"Lv. {level}", font=font_value, fill=(255, 255, 255))
    draw.text((bar_x, bar_y + bar_height + 5), f"XP : {xp}/{next_xp}", font=font_label, fill=(200, 200, 200))
    # Quiz score
    q_y = bar_y + 60
    draw.text((bar_x, q_y), "Score Quiz", font=font_label, fill=(200, 200, 200))
    draw.text((bar_x + 250, q_y), str(quiz_score), font=font_value, fill=(255, 215, 0))
    # Mini-games scores
    m_y_start = q_y + 40
    if mini_scores:
        draw.text((bar_x, m_y_start), "Mini‑jeux", font=font_label, fill=(200, 200, 200))
        offset = 0
        for game, val in mini_scores.items():
            # Human-readable names for mini-games
            mapping = {
                "animequiz": "Quiz",
                "higherlower": "Higher/Lower",
                "highermean": "Higher/Mean",
                "guessyear": "Guess Year",
                "guessepisodes": "Guess Episodes",
                "guessgenre": "Guess Genre",
                "duel": "Duel",
            }
            g_name = mapping.get(game, game.replace("_", " ").capitalize())
            draw.text(
                (bar_x + 20, m_y_start + 30 + offset * 28),
                f"{g_name}",
                font=font_label,
                fill=(160, 200, 255),
            )
            draw.text(
                (bar_x + 250, m_y_start + 30 + offset * 28),
                str(val),
                font=font_value,
                fill=(255, 175, 200),
            )
            offset += 1
    else:
        draw.text((bar_x, m_y_start), "Mini‑jeux", font=font_label, fill=(200, 200, 200))
        draw.text((bar_x + 250, m_y_start), "0", font=font_value, fill=(255, 175, 200))
    # Export
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf
