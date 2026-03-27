# modules/core.py
"""
Module core pour le AnimeBot.

Ce module centralise toutes les fonctionnalités essentielles :
- Gestion des fichiers et données persistantes (scores, niveaux, préférences)
- Interface avec l'API AniList (recherche, statistiques, épisodes)
- Génération d'images (cartes de profil, épisodes)
- Gestion des titres et correspondances
- Utilitaires de formatage et normalisation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
import re
import unicodedata
import random
import time
import difflib
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional, Dict, List, Set, Union, Tuple, Iterable
import sqlite3
import discord
import requests
import pytz
from zoneinfo import ZoneInfo
import aiohttp
import aiofiles
from babel.dates import format_datetime
from PIL import Image, ImageDraw, ImageFont
import io
from io import BytesIO  # utilisé par generate_profile_card


def _load_bot_version() -> str:
    """Lecture de `VERSION` à la racine du projet, sinon env `BOT_VERSION`, sinon `dev`."""
    try:
        root = Path(__file__).resolve().parent.parent
        vf = root / "VERSION"
        if vf.is_file():
            return vf.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return (os.getenv("BOT_VERSION") or "dev").strip() or "dev"


__version__ = _load_bot_version()

# ================= LOGGING =================
# Évite de dupliquer les handlers si bot.py a déjà appelé basicConfig.
if not logging.root.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
logger = logging.getLogger(__name__)
LOG = logger

# Verrou global pour lectures/écritures JSON (évite courses read-modify-write entre coroutines).
DATA_JSON_LOCK = threading.RLock()


def anilist_error_user_message() -> str:
    """Message Discord unifié quand l’API AniList est indisponible ou ne renvoie rien d’exploitable."""
    return (
        "❌ L’API AniList ne répond pas pour le moment. Réessaie dans quelques minutes."
    )

# ================= CONFIG & PATHS =================
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets')
_USER_URL_RE = re.compile(r"https?://(www\.)?anilist\.co/user/([^/?#]+)/?", re.I)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", "data/bot.db")
os.makedirs("data", exist_ok=True)

WINNER_FILE = os.path.join(DATA_DIR, "winner.json")
TITLES_FILE = os.path.join(DATA_DIR, "user_titles.json")  # chemin rendu cohérent
CACHE_FILE = os.path.join(DATA_DIR, "anime_titles.json")  # idem

class FileConfig:
    """Configuration des chemins de fichiers."""
    PREFERENCES   = os.path.join(DATA_DIR, "preferences.json")
    QUIZ_SCORES   = os.path.join(DATA_DIR, "quiz_scores.json")
    LINKED_USERS  = os.path.join(DATA_DIR, "linked_users.json")
    LEVELS        = os.path.join(DATA_DIR, "quiz_levels.json")
    TRACKER       = os.path.join(DATA_DIR, "anitracker.json")
    USER_SETTINGS = os.path.join(DATA_DIR, "user_settings.json")
    NOTIFIED      = os.path.join(DATA_DIR, "notified.json")
    LINKS         = os.path.join(DATA_DIR, "user_links.json")
    TITLE_CACHE   = os.path.join(DATA_DIR, "title_cache.json")
    WINNER        = os.path.join(DATA_DIR, "quiz_winner.json")
    MINI_SCORES   = os.path.join(DATA_DIR, "mini_scores.json")
    CONFIG        = os.path.join(DATA_DIR, "config.json")
    GUESSOP_SCORES  = os.path.join(DATA_DIR, "guessop_scores.json")
    GUESSCHAR_SCORES = os.path.join(DATA_DIR, "guesschar_scores.json")
    GUESS_GENRE_SANCTIONS = os.path.join(DATA_DIR, "guess_genre_sanctions.json")
    OWNER_TELEMETRY = os.path.join(DATA_DIR, "owner_telemetry.json")
    BOSS_RAID = os.path.join(DATA_DIR, "boss_raid.json")

_AIRING_SORT_FIX = {
    "AIRING_AT": "TIME",
    "AIRING_AT_DESC": "TIME_DESC",
}

# Variables d'environnement et constantes
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ANILIST_USERNAME = os.getenv("ANILIST_USERNAME", "Zirnoixdcoco")
_ANILIST_USERNAME_RE = re.compile(r"^[A-Za-z0-9_][-A-Za-z0-9_]{1,31}$")
TIMEZONE = pytz.timezone(os.getenv("BOT_TIMEZONE", "Europe/Paris"))

# Constantes pour les dates
JOURS_FR = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
    "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi",
    "Sunday": "Dimanche"
}

# Aligné sur datetime.weekday() : 0 = lundi … 6 = dimanche
JOURS_SEMAINE_FR = (
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"
)

# Émojis pour les genres
GENRE_EMOJIS = {
    "Action": "⚔️", "Comedy": "😂", "Drama": "🎭", "Fantasy": "🧙‍♂️",
    "Romance": "💕", "Sci-Fi": "🚀", "Horror": "👻", "Mystery": "🕵️",
    "Sports": "🏅", "Music": "🎵", "Slice of Life": "🍃",
    "Adventure": "🌍", "Supernatural": "🔮", "Mecha": "🤖",
    "Psychological": "🧠", "Thriller": "🔪"
}

# Titres de niveaux (paliers de 5)
LEVEL_TITLES_QUIZ = [
    (0, "👶 Nouveau"), (5, "🌱 Apprenti"), (10, "📘 Amateur"), (15, "📚 Otaku Confirmé"),
    (20, "🎯 Expert"), (25, "🔥 Maître Otaku"), (30, "🧠 Sensei"), (35, "🧩 Stratège"),
    (40, "🏆 Champion"), (45, "🌟 Légende Locale"), (50, "💎 Légende Nationale"),
    (55, "🗿 Icône Anime"), (60, "🐉 Mythe"), (65, "🛐 Dieu Otaku"),
    (70, "☄️ Divinité Universelle"), (75, "🔮 Omniscient Otaku"),
    (80, "⚡ Maître des Éclairs"), (85, "🌌 Voyageur Galactique"),
    (90, "🏮 Gardien des Animes"), (95, "🎭 Maître des Illusions"),
    (100, "👑 Roi des Otakus")
]

# Titres niveau GLOBAL (XP)
LEVEL_TITLES_GLOBAL = [
    (0, "👶 Novice"), (3, "🌱 Initié"), (6, "📗 Débutant"), (9, "🔧 Pratiquant"),
    (12, "🧭 Explorateur"), (15, "🎯 Approuvé"), (20, "⚔️ Aspirant"), (25, "🏹 Disciple"),
    (30, "🛡️ Chevalier"), (37, "🧠 Stratège"), (44, "🔥 Maître"), (51, "🌪️ Virtuose"),
    (58, "💎 Élite"), (65, "🌟 Héroïque"), (72, "🐉 Archon"), (79, "⚡ Dominant"),
    (86, "🌌 Mythique"), (93, "🏆 Parangon"), (100, "👑 Souverain"), (107, "🗼 Éminence"),
    (114, "🜲 Arcaniste"), (121, "🪽 Séraphin"), (128, "☄️ Sidéral"),
    (135, "🜚 Transcendant"), (142, "🛐 Divin"), (150, "♾️ Apothéose"),
]

_ANILIST_CACHE = {
    "profile": {},      # { key: {"ts": <epoch>, "data": {...}} }
    "list_count": {},   # total d'entrées de la liste
    "upcoming": {},     # prochains épisodes
}
_TTL_SEC = int(os.getenv("ANILIST_TTL_HOURS", "6")) * 3600

def _fresh(bucket: str, key: str) -> bool:
    ent = _ANILIST_CACHE[bucket].get(key)
    return bool(ent) and (time.time() - ent["ts"] < _TTL_SEC)

# ================= JSON HELPERS =================
async def translate_text(text: str, target_lang: str = "FR") -> str:
    """Traduit du texte via DeepL (si clé présente)."""
    if not DEEPL_API_KEY:
        LOG.warning("Clé API DeepL manquante — traduction désactivée.")
        return text
    url = "https://api-free.deepl.com/v2/translate"
    params = {"auth_key": DEEPL_API_KEY, "text": text, "target_lang": target_lang}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=params) as resp:
                if resp.status != 200:
                    LOG.error(f"Erreur DeepL ({resp.status}) : {await resp.text()}")
                    return text
                data = await resp.json()
                return data["translations"][0]["text"]
    except Exception as e:
        LOG.error(f"Erreur traduction DeepL : {e}")
        return text

def load_titles():
    return load_json(TITLES_FILE, {})


def save_titles(titles):
    save_json(TITLES_FILE, titles)


def load_json(path: str, default: Any) -> Any:
    with DATA_JSON_LOCK:
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement de {path}: {e}")
            return default


def save_json(path: str, data: Any) -> None:
    """Écriture atomique (fichier temporaire + replace) sous verrou pour éviter fichiers tronqués."""
    try:
        with DATA_JSON_LOCK:
            d = os.path.dirname(path) or "."
            os.makedirs(d, exist_ok=True)
            tmp = f"{path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de {path}: {e}")

# ================= SCORES / NIVEAUX =================
def xp_for_next_level(level: int) -> int:
    base_xp = 50
    growth = 1.08
    return int(base_xp * (growth ** level))

def load_scores() -> dict:
    return load_json(FileConfig.QUIZ_SCORES, {})

def save_scores(scores: dict) -> None:
    save_json(FileConfig.QUIZ_SCORES, scores)

def load_levels() -> dict:
    return load_json(FileConfig.LEVELS, {})

def save_levels(data: dict) -> None:
    save_json(FileConfig.LEVELS, data)

async def add_xp(bot, channel, user_id: int, amount: int, announce: bool = True):
    """
    Ajoute de l'XP, gère le level-up (avec XP "reste" après passage),
    annonce optionnelle quand le **titre global** change (pas à chaque niveau intermédiaire),
    et DISPATCH l'événement 'level_up' si au moins un niveau a été gagné.
    """
    with DATA_JSON_LOCK:
        levels = load_levels()
        key = str(user_id)
        data = levels.get(key, {"xp": 0, "level": 0})

        old_level = int(data.get("level", 0))
        old_title = get_title_for_global_level(old_level)

        data["xp"] = int(data.get("xp", 0)) + int(amount)

        leveled = False
        while True:
            need = xp_for_next_level(int(data["level"]))
            if data["xp"] < need:
                break
            data["xp"] -= need
            data["level"] = int(data["level"]) + 1
            leveled = True

        levels[key] = data
        save_levels(levels)

        new_level = int(data["level"])
        new_title = get_title_for_global_level(new_level)

    # 🔔 annonce : salon dédié serveur si configuré, sinon salon où l’XP a été gagnée
    announce_ch = channel
    if announce and channel is not None:
        g = getattr(channel, "guild", None)
        if g is not None:
            lid = get_guild_levelup_channel_id(g.id)
            if lid:
                alt = bot.get_channel(lid)
                if isinstance(alt, discord.TextChannel):
                    announce_ch = alt
    if announce and announce_ch is not None and new_title != old_title:
        try:
            await announce_ch.send(
                f"🎉 **<@{user_id}>** débloque un **nouveau titre** : **{new_title}** _(niveau **{new_level}**)_ !"
            )
        except Exception:
            pass

    # ✅ DISPATCH de l'event 'level_up' (consommé par le cog Engagement)
    if leveled:
        try:
            bot.dispatch("level_up", user_id, new_level)
        except Exception:
            pass

    return {
        "leveled": leveled,
        "old_level": old_level,
        "new_level": new_level,
        "old_title": old_title,
        "new_title": new_title,
    }


async def announce_quiz_title_if_changed(
    bot,
    channel,
    user_id: int,
    old_score: int,
    new_score: int,
) -> None:
    """
    Annonce un **nouveau titre quiz** (paliers LEVEL_TITLES_QUIZ) dans le salon `/setlevelupchannel`
    s’il est défini, sinon dans le salon où le score a été mis à jour.
    Uniquement en cas de **progression** (score strictement supérieur) et si le titre change.
    """
    old_score = int(old_score)
    new_score = int(new_score)
    if new_score <= old_score:
        return
    old_t = get_title_for_quiz_score(old_score)
    new_t = get_title_for_quiz_score(new_score)
    if old_t == new_t:
        return
    announce_ch = channel
    if channel is not None:
        g = getattr(channel, "guild", None)
        if g is not None:
            lid = get_guild_levelup_channel_id(g.id)
            if lid:
                alt = bot.get_channel(lid)
                if isinstance(alt, discord.TextChannel):
                    announce_ch = alt
    if announce_ch is None:
        return
    try:
        await announce_ch.send(
            f"📚 **<@{user_id}>** débloque un **nouveau titre quiz** : **{new_t}** _(score **{new_score}** pts)_ !"
        )
    except Exception:
        pass


def get_title_for_global_level(level: int) -> str:
    current_title = LEVEL_TITLES_GLOBAL[0][1]
    for req_level, title in LEVEL_TITLES_GLOBAL:
        if level >= req_level:
            current_title = title
        else:
            break
    return current_title

def get_title_for_quiz_score(score: int) -> str:
    current_title = LEVEL_TITLES_QUIZ[0][1]
    for req_score, title in LEVEL_TITLES_QUIZ:
        if score >= req_score:
            current_title = title
        else:
            break
    return current_title

# ================= FORMAT DATES / ANILIST HELPERS =================
def format_airing_datetime_fr(ts: int, tz_name: str = "Europe/Paris") -> str:
    if not ts:
        return "date inconnue"
    dt_local = datetime.fromtimestamp(ts, tz=ZoneInfo(tz_name))
    months = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
              "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    weekdays = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    wd = weekdays[dt_local.weekday()]
    mo = months[dt_local.month - 1]
    return f"{wd} {dt_local.day} {mo} {dt_local:%H:%M}"

# ================= ANIList API / QUERIES =================
# --- WHITELIST SERVEUR (séries suivies) ---
def _ensure_guild_airings_table():
    conn = _db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guild_airings (
            guild_id   INTEGER NOT NULL,
            media_id   INTEGER NOT NULL,
            added_at   INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            PRIMARY KEY (guild_id, media_id)
        )
    """)
    conn.commit()

def guild_airings_ids(guild_id: int) -> List[int]:
    _ensure_guild_airings_table()
    conn = _db()
    rows = conn.execute("SELECT media_id FROM guild_airings WHERE guild_id=?", (int(guild_id),)).fetchall()
    return [r[0] for r in rows]

def guild_airings_add(guild_id: int, media_id: int) -> bool:
    _ensure_guild_airings_table()
    conn = _db()
    try:
        conn.execute("INSERT OR IGNORE INTO guild_airings (guild_id, media_id) VALUES (?,?)", (int(guild_id), int(media_id)))
        conn.commit()
        # retourne True s'il y a eu insertion
        cur = conn.execute("SELECT changes()").fetchone()
        return bool(cur and cur[0])
    except Exception:
        return False

def guild_airings_remove(guild_id: int, media_id: int) -> bool:
    _ensure_guild_airings_table()
    conn = _db()
    cur = conn.execute("DELETE FROM guild_airings WHERE guild_id=? AND media_id=?", (int(guild_id), int(media_id)))
    conn.commit()
    return cur.rowcount > 0

def get_airings_global(days: int = 14, limit: int = 200) -> List[dict]:
    """
    Planning global des sorties (tous animes, non-adult) sur [now ; now+days].
    Retourne une liste triée par airingAt asc:
      {airingAt, episode, media{ id, title{...}, siteUrl, coverImage, genres }}
    """
    days = max(1, min(31, int(days or 14)))
    now = int(time.time())
    end = now + days * 86400

    out: List[dict] = []
    page = 1
    per_page = 50
    # On plafonne le nombre total d'entrées pour éviter le spam
    remaining = max(1, limit)

    query = """
    query ($page:Int!, $perPage:Int!, $now:Int!, $end:Int!) {
      Page(page:$page, perPage:$perPage) {
        pageInfo { hasNextPage }
        airingSchedules(
          notYetAired: true,
          airingAt_greater: $now,
          airingAt_lesser:  $end,
          sort: [TIME]
        ) {
          airingAt
          episode
          media {
            id
            siteUrl
            title { romaji english native }
            coverImage { large }
            genres
            isAdult
          }
        }
      }
    }
    """

    while remaining > 0:
        data = query_anilist(query, {
            "page": page, "perPage": per_page, "now": now, "end": end
        }) or {}
        pg = (data.get("data") or {}).get("Page") or {}
        items = pg.get("airingSchedules") or []

        # filtre sécurité (non-adulte)
        for s in items:
            m = s.get("media") or {}
            if m.get("isAdult"):
                continue
            out.append({
                "airingAt": s.get("airingAt"),
                "episode": s.get("episode"),
                "media": {
                    "id": m.get("id"),
                    "siteUrl": m.get("siteUrl"),
                    "title": m.get("title") or {},
                    "cover": (m.get("coverImage") or {}).get("large"),
                    "genres": m.get("genres") or [],
                }
            })
            remaining -= 1
            if remaining <= 0:
                break

        if remaining <= 0 or not (pg.get("pageInfo") or {}).get("hasNextPage"):
            break
        page += 1

    out = [x for x in out if isinstance(x.get("airingAt"), int)]
    out.sort(key=lambda x: x["airingAt"])
    return out


def _best_anilist_cover_url(media: dict | None) -> str | None:
    """URL cover AniList (extraLarge > large > medium) ; évite vignette vide si seul `large` manque."""
    if not media:
        return None
    ci = media.get("coverImage")
    if isinstance(ci, str) and ci.strip():
        return ci.strip()
    if isinstance(ci, dict):
        return (
            ci.get("extraLarge")
            or ci.get("large")
            or ci.get("medium")
        )
    return None


def _fetch_media_alert_candidates_batch(media_ids: List[int], now: int, grace: int) -> List[dict]:
    """
    Pour chaque media_id, interroge nextAiringEpisode : si la date est passée mais encore dans
    `grace` secondes après la diffusion, l’épisode est « éligible » à une annonce sortie.
    (Les grilles globales AniList ne garantissent pas les créneaux passés ; le détail Media est fiable.)
    """
    if not media_ids:
        return []
    parts: List[str] = []
    for i, mid in enumerate(media_ids):
        parts.append(
            f"a{i}: Media(id: {int(mid)}, type: ANIME) {{ id siteUrl title {{ romaji english native }} "
            f"coverImage {{ extraLarge large medium }} genres nextAiringEpisode {{ episode airingAt }} }}"
        )
    query = "query { " + " ".join(parts) + " }"
    data = query_anilist(query, {}) or {}
    payload = (data.get("data") or {})
    out: List[dict] = []
    for i, _mid in enumerate(media_ids):
        m = payload.get(f"a{i}")
        if not m:
            continue
        nae = m.get("nextAiringEpisode") or {}
        at = nae.get("airingAt")
        if not isinstance(at, int):
            continue
        if at > now:
            continue
        if now > at + grace:
            continue
        t = m.get("title") or {}
        out.append(
            {
                "airingAt": at,
                "episode": nae.get("episode"),
                "media": {
                    "id": m.get("id"),
                    "siteUrl": m.get("siteUrl"),
                    "title": t,
                    "cover": _best_anilist_cover_url(m),
                    "genres": m.get("genres") or [],
                },
            }
        )
    return out


def _fetch_airing_schedules_past_window(
    start_ts: int,
    end_ts: int,
    *,
    limit_pages: int = 25,
) -> List[dict]:
    """
    Créneaux dont airingAt est dans ]start_ts, end_ts] (AniList « airingSchedules »).
    Sert de filet de sécurité : après diffusion, `nextAiringEpisode` peut déjà pointer vers le futur,
    ce qui faisait rater l’annonce basée uniquement sur Media.nextAiringEpisode.
    """
    if start_ts >= end_ts:
        return []
    out: List[dict] = []
    page = 1
    per_page = 50
    for _ in range(max(1, int(limit_pages))):
        query = """
        query ($page:Int!, $perPage:Int!, $start:Int!, $end:Int!) {
          Page(page:$page, perPage:$perPage) {
            pageInfo { hasNextPage }
            airingSchedules(
              airingAt_greater: $start,
              airingAt_lesser: $end,
              sort: [TIME]
            ) {
              airingAt
              episode
              media {
                id
                siteUrl
                title { romaji english native }
                coverImage { extraLarge large medium }
                genres
                isAdult
              }
            }
          }
        }
        """
        data = query_anilist(query, {"page": page, "perPage": per_page, "start": start_ts, "end": end_ts}) or {}
        if isinstance(data, dict) and data.get("errors"):
            LOG.warning(
                "airingSchedules past window: %s",
                str(data.get("errors"))[:280],
            )
            break
        pg = (data.get("data") or {}).get("Page") or {}
        items = pg.get("airingSchedules") or []
        for s in items:
            m = s.get("media") or {}
            if m.get("isAdult"):
                continue
            out.append(
                {
                    "airingAt": s.get("airingAt"),
                    "episode": s.get("episode"),
                    "media": {
                        "id": m.get("id"),
                        "siteUrl": m.get("siteUrl"),
                        "title": m.get("title") or {},
                        "cover": _best_anilist_cover_url(m),
                        "genres": m.get("genres") or [],
                    },
                }
            )
        if not (pg.get("pageInfo") or {}).get("hasNextPage"):
            break
        page += 1
    return [x for x in out if isinstance(x.get("airingAt"), int)]


def get_recent_airings_for_guild(
    guild_id: int,
    *,
    grace_sec: int = 18 * 3600,
    chunk_size: int = 10,
) -> List[dict]:
    """Animes de la whitelist `/airings` : épisode vient de passer (fenêtre de rattrapage)."""
    ids: Set[int] = {int(x["media_id"]) for x in guild_whitelist_list(guild_id)}
    ids |= {int(x) for x in guild_airings_ids(guild_id)}
    if not ids:
        return []
    now = int(time.time())
    grace = int(grace_sec)
    start_ts = now - grace
    id_list = sorted(ids)
    out: List[dict] = []
    seen: Set[tuple[int, int]] = set()
    cs = max(1, min(25, int(chunk_size)))
    for i in range(0, len(id_list), cs):
        chunk = id_list[i : i + cs]
        for item in _fetch_media_alert_candidates_batch(chunk, now, grace):
            mid = int((item.get("media") or {}).get("id") or 0)
            ep = item.get("episode")
            try:
                ek = int(float(ep))
            except Exception:
                ek = 0
            seen.add((mid, ek))
            out.append(item)

    try:
        for item in _fetch_airing_schedules_past_window(start_ts, now, limit_pages=25):
            m = item.get("media") or {}
            mid = m.get("id")
            if mid is None:
                continue
            imid = int(mid)
            if imid not in ids:
                continue
            ep = item.get("episode")
            try:
                ek = int(float(ep))
            except Exception:
                ek = 0
            if (imid, ek) in seen:
                continue
            seen.add((imid, ek))
            t = m.get("title") or {}
            out.append(
                {
                    "airingAt": item.get("airingAt"),
                    "episode": ep,
                    "media": {
                        "id": m.get("id"),
                        "siteUrl": m.get("siteUrl"),
                        "title": t,
                        "cover": _best_anilist_cover_url(m),
                        "genres": m.get("genres") or [],
                    },
                }
            )
    except Exception as e:
        LOG.warning("get_recent_airings_for_guild schedule fallback: %s", e)
    return out


def airing_item_to_card_dict(item: dict, *, tz_name: str = "Europe/Paris") -> dict:
    """Uniformise un créneau `get_airings_*` pour `modules.image.generate_next_card` / alertes."""
    m = item.get("media") or {}
    t = m.get("title") or {}
    ts = int(item.get("airingAt") or 0)
    ep = item.get("episode")
    try:
        ep_disp: int | str = int(float(ep)) if ep is not None else "?"
    except Exception:
        ep_disp = ep if ep is not None else "?"
    when_str = format_airing_datetime_fr(ts, tz_name) if ts else "date inconnue"
    cov = m.get("cover")
    if not cov:
        cov = _best_anilist_cover_url(m)
    ci = m.get("coverImage") or {}
    cover_urls: list[str] = []
    if isinstance(ci, dict):
        for k in ("extraLarge", "large", "medium"):
            u = ci.get(k)
            if u and u not in cover_urls:
                cover_urls.append(u)
    if cov and cov not in cover_urls:
        cover_urls.insert(0, cov)
    elif not cover_urls and cov:
        cover_urls = [cov]
    return {
        "title_romaji": t.get("romaji"),
        "title_english": t.get("english"),
        "title_native": t.get("native"),
        "episode": ep_disp,
        "airingAt": ts,
        "cover": cov,
        "cover_urls": cover_urls,
        "genres": m.get("genres") or [],
        "when": when_str,
        "siteUrl": m.get("siteUrl"),
    }


def get_airings_for_guild(guild_id: int, *, days: int = 7, limit: int = 200) -> List[dict]:
    """
    Retourne les sorties à venir filtrées par la whitelist du serveur.
    Utilise **guild_whitelist** (rempli par /airings all, add, etc.) et fusionne
    l’ancienne table **guild_airings** si elle contenait encore des IDs.
    Forme: [{airingAt, episode, media{ id, siteUrl, title{...}, cover, genres }}]
    """
    ids: Set[int] = {int(x["media_id"]) for x in guild_whitelist_list(guild_id)}
    ids |= {int(x) for x in guild_airings_ids(guild_id)}
    if not ids:
        return []
    all_items = get_airings_global(days=days, limit=max(limit, 200))
    out = [it for it in all_items if ((it.get("media") or {}).get("id") in ids)]
    return out[:limit]

def get_next_for_guild(guild_id: int) -> Optional[dict]:
    """
    Premier item (le plus proche) de la whitelist serveur.
    """
    items = get_airings_for_guild(guild_id, days=14, limit=500)
    return items[0] if items else None

# ================= AIRINGS — Whitelist par serveur =================

def search_media(query: str, limit: int = 10) -> List[dict]:
    """Recherche AniList Media(type:ANIME). Retourne [{id,title{...},siteUrl,coverImage{large}}]."""
    q = """
    query ($q:String, $page:Int!, $perPage:Int!){
      Page(page:$page, perPage:$perPage){
        media(search:$q, type:ANIME, sort:POPULARITY_DESC){
          id
          siteUrl
          title{ romaji english native }
          coverImage{ large }
        }
      }
    }"""
    data = query_anilist(q, {"q": query, "page": 1, "perPage": max(1, min(25, limit or 10))}) or {}
    page = (data.get("data") or {}).get("Page") or {}
    items = page.get("media") or []
    out = []
    for m in items:
        out.append({
            "id": m.get("id"),
            "siteUrl": m.get("siteUrl"),
            "title": (m.get("title") or {}),
            "coverImage": (m.get("coverImage") or {}),
        })
    return out

def _ensure_guild_whitelist_table():
    conn = _db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guild_whitelist (
            guild_id   INTEGER NOT NULL,
            media_id   INTEGER NOT NULL,
            title_romaji TEXT,
            site_url     TEXT,
            cover        TEXT,
            added_at   INTEGER NOT NULL,
            PRIMARY KEY (guild_id, media_id)
        )
    """)
    conn.commit()

def guild_whitelist_add(guild_id: int, media_id: int) -> dict | None:
    """Ajoute un media dans la whitelist du serveur. Retourne infos du média pour feedback."""
    _ensure_guild_whitelist_table()
    # récupérer infos du média
    q = """
    query ($id:Int){
      Media(id:$id, type:ANIME){
        id
        siteUrl
        title{ romaji english native }
        coverImage{ large }
      }
    }"""
    data = query_anilist(q, {"id": int(media_id)}) or {}
    m = ((data.get("data") or {}).get("Media")) or None
    if not m:
        return None
    title = (m.get("title") or {}).get("romaji") or (m.get("title") or {}).get("english") or (m.get("title") or {}).get("native") or str(media_id)
    site = m.get("siteUrl")
    cover = (m.get("coverImage") or {}).get("large")
    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO guild_whitelist (guild_id, media_id, title_romaji, site_url, cover, added_at) VALUES (?,?,?,?,?,strftime('%s','now'))",
        (int(guild_id), int(media_id), title, site, cover)
    )
    conn.commit()
    return {"id": media_id, "title": m.get("title") or {}, "siteUrl": site, "cover": cover}


def guild_whitelist_add_from_snapshot(guild_id: int, media: dict) -> bool:
    """
    Ajoute un média à la whitelist sans requête AniList (données déjà connues,
    ex. objet `media` d’un airing de `get_airings_global`).
    Retourne True si une **nouvelle** ligne a été insérée (déjà présent → False).
    """
    _ensure_guild_whitelist_table()
    mid = int((media or {}).get("id") or 0)
    if not mid:
        return False
    t = (media.get("title") or {})
    title = t.get("romaji") or t.get("english") or t.get("native") or str(mid)
    site = media.get("siteUrl") or ""
    cov = media.get("cover")
    if not cov and isinstance(media.get("coverImage"), dict):
        cov = (media.get("coverImage") or {}).get("large")
    cover = cov or ""
    conn = _db()
    cur = conn.execute(
        "INSERT OR IGNORE INTO guild_whitelist (guild_id, media_id, title_romaji, site_url, cover, added_at) VALUES (?,?,?,?,?,strftime('%s','now'))",
        (int(guild_id), mid, title, site, cover),
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def guild_whitelist_remove(guild_id: int, media_id: int) -> bool:
    _ensure_guild_whitelist_table()
    conn = _db()
    cur = conn.execute("DELETE FROM guild_whitelist WHERE guild_id=? AND media_id=?", (int(guild_id), int(media_id)))
    conn.commit()
    return cur.rowcount > 0

def guild_whitelist_list(guild_id: int) -> List[dict]:
    _ensure_guild_whitelist_table()
    conn = _db()
    rows = conn.execute("SELECT media_id, title_romaji, site_url, cover, added_at FROM guild_whitelist WHERE guild_id=? ORDER BY added_at DESC", (int(guild_id),)).fetchall()
    out = []
    for r in rows:
        out.append({
            "media_id": r[0], "title_romaji": r[1], "siteUrl": r[2], "cover": r[3], "added_at": r[4]
        })
    return out

def filter_airings_for_guild(guild_id: int, items: List[dict]) -> List[dict]:
    """Filtre une liste d'airings (get_airings_global) selon la whitelist du serveur."""
    wl = set(x["media_id"] for x in guild_whitelist_list(guild_id))
    out = []
    for it in (items or []):
        mid = ((it.get("media") or {}).get("id"))
        if mid in wl:
            out.append(it)
    return out

def _normalize_airing_sort(query: str) -> str:
    """
    Rend compatibles les vieux enums AniList :
      - AIRING_AT[_DESC] -> TIME[_DESC]
      - Force le format liste si on voit 'sort: TIME' ou 'sort: TIME_DESC'
      - Gère les cas avec listes multiples (ex: sort: [AIRING_AT, EPISODE_DESC])
      - Insensible aux espaces
    """
    if not isinstance(query, str):
        return query

    q = query

    # 1) Remplace tous les tokens enum obsolètes, y compris dans des listes multiples
    #    (on remplace d'abord _DESC pour ne pas transformer deux fois)
    q = re.sub(r"\bAIRING_AT_DESC\b", "TIME_DESC", q)
    q = re.sub(r"\bAIRING_AT\b", "TIME", q)

    # 2) Si on trouve sort: TIME (sans crochets), on met des crochets
    #    (on évite de re-bracket si c'est déjà une liste)
    q = re.sub(r"(sort\s*:\s*)(?!\[)\s*(TIME_DESC|TIME)\b", r"\1[\2]", q)

    # 3) Normalise des variantes d'espaces (facultatif mais propre)
    #    Pas de changement sémantique, juste clean
    return q
def filter_titles_for_quiz(
    animes: list,
    *,
    min_year: int = 1986,
    min_score: int = 50,          # 50 = 5/10 ; mets 40 pour 4/10
    allowed_countries: set[str] = {"JP"},
) -> list:
    """
    Garde uniquement les animés:
      - countryOfOrigin ∈ allowed_countries (par défaut: Japon)
      - start year >= min_year (fallback sur seasonYear)
      - meanScore >= min_score (fallback averageScore)
    """
    if not animes:
        return []

    out = []
    for a in animes:
        try:
            # pays
            country = (a.get("countryOfOrigin") or "").upper()
            if allowed_countries and country not in allowed_countries:
                continue

            # année
            y = None
            sd = a.get("startDate") or {}
            if isinstance(sd, dict):
                y = sd.get("year")
            if not y:
                y = a.get("seasonYear")
            if not y:
                # parfois AniList met l'info dans 'year' plat
                y = a.get("year")
            try:
                y = int(y)
            except Exception:
                y = None
            if y is None or y < min_year:
                continue

            # score
            score = a.get("meanScore")
            if score is None:
                score = a.get("averageScore")  # certains dumps utilisent averageScore
            try:
                score = int(score)
            except Exception:
                score = None
            if score is None or score < min_score:
                continue

            out.append(a)
        except Exception:
            # on skippe silencieusement les entrées bizarres
            continue

    return out

def _synthesize_profile_from_list(username: str) -> dict | None:
    """
    Construit un 'profil' (count, minutesWatched, meanScore, favoriteGenre)
    à partir de la MediaListCollection (entries) quand User.statistics.anime est indisponible.
    """
    q = """
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME) {
        lists {
          entries {
            status
            score
            progress
            media {
              id
              duration
              episodes
              genres
            }
          }
        }
      }
    }"""
    data = query_anilist(q, {"name": username})
    coll = data and data.get("data", {}).get("MediaListCollection")
    if not coll:
        return None

    total_count = 0
    minutes = 0
    scores = []
    genre_counts = {}

    def clamp_int(x, default=0):
        try:
            return int(x)
        except Exception:
            return default

    for lst in coll.get("lists") or []:
        for e in lst.get("entries") or []:
            status = (e.get("status") or "").upper()
            score = e.get("score")
            progress = clamp_int(e.get("progress"))
            media = e.get("media") or {}
            duration = clamp_int(media.get("duration"))      # minutes/épisode
            episodes = clamp_int(media.get("episodes"))
            genres = media.get("genres") or []

            # count: on compte completed comme "vu" (tu peux inclure REPEATING si tu veux)
            if status in {"COMPLETED"}:
                total_count += 1
                # genres favoris: compter surtout sur ce qui est complété
                for g in genres:
                    genre_counts[g] = genre_counts.get(g, 0) + 1

            # temps total (approx): min(progress, episodes) * duration
            if duration > 0:
                seen_eps = progress if episodes <= 0 else min(progress, episodes)
                if seen_eps > 0:
                    minutes += seen_eps * duration

            # moyenne des scores non nuls
            try:
                s = float(score or 0)
                if s > 0:
                    scores.append(s)
            except Exception:
                pass

    mean = round(sum(scores) / len(scores), 1) if scores else 0.0
    favorite_genre = max(genre_counts, key=genre_counts.get) if genre_counts else None

    return {
        "count": total_count,
        "minutesWatched": minutes,
        "meanScore": mean,
        "favoriteGenre": favorite_genre,
        "_approx": True,  # drapeau pour l’UI
    }

def get_profile_stats(username: str, *, force: bool = False) -> dict:
    """
    Retourne le dict AniList statistics.anime si dispo,
    sinon un profil approximé synthétisé depuis la liste (_approx=True).
    Ne lève pas d'exception ; retourne {} en dernier recours.
    """
    # (Si tu as un cache maison, place ton check ici et ton set en bas)
    q = """
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
    }"""
    stats = {}
    try:
        data = query_anilist(q, {"name": username})
        user = data and data.get("data", {}).get("User")
        if user and user.get("statistics") and user["statistics"].get("anime"):
            stats = dict(user["statistics"]["anime"])
            stats["_approx"] = False
            genres = stats.get("genres")
            if not stats.get("favoriteGenre") and isinstance(genres, list) and genres:
                try:
                    top = max(genres, key=lambda g: int(g.get("count") or 0))
                    if top and top.get("genre"):
                        stats["favoriteGenre"] = top["genre"]
                except Exception:
                    pass
    except Exception:
        stats = {}

    # fallback si vide / 0 partout
    try:
        if (not stats) or (
            int(stats.get("count") or 0) == 0
            and int(stats.get("minutesWatched") or 0) == 0
            and float(stats.get("meanScore") or 0.0) == 0.0
        ):
            synth = _synthesize_profile_from_list(username)
            if synth:
                stats = synth
    except Exception:
        pass

    # (Si tu as un cache maison, pose-le ici)
    return stats or {}

def get_list_total_entries(username: str, *, force: bool = False) -> int:
    """
    Nombre total d'entrées dans la MediaListCollection (tous statuts confondus).
    Ne lève pas ; 0 si erreur.
    """
    q = """
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME) {
        lists { entries { id } }
      }
    }"""
    total = 0
    try:
        data = query_anilist(q, {"name": username})
        coll = data and data.get("data", {}).get("MediaListCollection")
        if coll:
            for lst in coll.get("lists") or []:
                total += len(lst.get("entries") or [])
    except Exception:
        total = 0
    return int(total)
    
def _db_conn():
    """Connexion SQLite unique (DB_PATH) : liens AniList + anti-doublon d’alertes épisode."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS anilist_links (
        discord_id INTEGER PRIMARY KEY,
        username   TEXT NOT NULL,
        linked_at  INTEGER DEFAULT (strftime('%s','now'))
    )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posted_events (
            media_id    INTEGER NOT NULL,
            episode     INTEGER NOT NULL,
            channel_id  INTEGER NOT NULL,
            kind        TEXT    NOT NULL,
            posted_at   INTEGER NOT NULL,
            PRIMARY KEY (media_id, episode, channel_id, kind)
        )
    """)
    return conn
    
def _coerce_anilist_username(v) -> str | None:
    """Essaie d’extraire un pseudo à partir d’un str ou d’un dict historique."""
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("@"):
            s = s[1:]
        return s or None
    if isinstance(v, dict):
        # Ancien format possible: {"username": "foo"} / {"anilist": "foo"} / {"name": "foo"}
        for k in ("anilist", "username", "name"):
            val = v.get(k)
            if isinstance(val, str) and val.strip():
                s = val.strip()
                if s.startswith("@"):
                    s = s[1:]
                return s
    return None

def is_plausible_anilist_username(s: str) -> bool:
    """Filtre très permissif mais sans espaces/char exotiques."""
    if not isinstance(s, str):
        return False
    return bool(_ANILIST_USERNAME_RE.fullmatch(s))

def get_linked_anilist_usernames_bulk() -> list[str]:
    """
    Pseudos AniList liés (JSON + table SQLite), filtrés « plausibles ».
    Évite de lancer des requêtes 404.
    """
    ok: set[str] = set()
    try:
        links = load_links()  # {discord_id: value}
        for v in (links or {}).values():
            s = _coerce_anilist_username(v)
            if s and is_plausible_anilist_username(s):
                ok.add(s)
    except Exception:
        pass
    try:
        with _db_conn() as con:
            for (u,) in con.execute("SELECT username FROM anilist_links"):
                if u and is_plausible_anilist_username(str(u)):
                    ok.add(str(u))
    except Exception:
        pass
    return sorted(ok)

def get_upcoming_episodes_for_discord(discord_id: int) -> List[dict]:
    username = get_linked_username(discord_id)
    if not username:
        return []
    return get_upcoming_episodes(username)

def _normalize_name(s: str) -> str:
    s = (s or "").strip()
    return unicodedata.normalize("NFKC", s)

def query_anilist_user(input_str: str) -> dict | None:
    """
    Résout un utilisateur AniList à partir de :
      - un ID numérique ("12345")
      - une URL de profil ("https://anilist.co/user/Truc")
      - un pseudo (insensible aux espaces/Unicode normalisé)
    Retourne {'id': int, 'name': str} ou None.
    """
    raw = (input_str or "").strip()
    if not raw:
        return None

    m = _USER_URL_RE.match(raw)
    if m:
        raw = m.group(2)

    # ID numérique
    if raw.isdigit():
        q = "query ($id: Int){ User(id:$id){ id name } }"
        try:
            data = query_anilist(q, {"id": int(raw)})
            u = data.get("data", {}).get("User")
            return {"id": u["id"], "name": u["name"]} if u else None
        except Exception:
            return None

    # Pseudo
    name = _normalize_name(raw)
    q = "query ($name: String){ User(name:$name){ id name } }"
    try:
        data = query_anilist(q, {"name": name})
        u = data.get("data", {}).get("User")
        return {"id": u["id"], "name": u["name"]} if u else None
    except Exception:
        return None

# dans modules/core.py, remplace la fin de query_anilist par ça:
def query_anilist(query: str, variables: dict = None) -> dict:
    url = "https://graphql.anilist.co"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    query = _normalize_airing_sort(query)
    payload = {"query": query, "variables": variables or {}}

    # Simple retry/backoff sur 429/5xx
    max_tries = 4
    backoff = 0.8  # secondes

    for attempt in range(1, max_tries + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)

            # essaie de parser
            try:
                j = resp.json()
            except Exception:
                LOG.warning("[AniList] Non-JSON response (HTTP %s): %s", resp.status_code, resp.text[:300])
                j = {}

            # 429: respecte Retry-After si présent, puis retry (DEBUG tant qu’on retente ; WARNING si échec final)
            if resp.status_code == 429:
                retry_after = 0.0
                try:
                    retry_after = float(resp.headers.get("Retry-After", "0"))
                except Exception:
                    retry_after = 0.0
                if attempt < max_tries:
                    LOG.debug(
                        "[AniList] HTTP 429 (tentative %s/%s), attente %.1fs — %s",
                        attempt, max_tries, retry_after if retry_after > 0 else backoff, str(j)[:200],
                    )
                    time.sleep(retry_after if retry_after > 0 else backoff)
                    backoff *= 1.8
                    continue
                LOG.warning("[AniList] HTTP 429 après %s tentatives — %s", max_tries, str(j)[:300])
                return j or {}

            # autres codes ≠ 200
            if resp.status_code != 200:
                if resp.status_code == 404:
                    LOG.debug("[AniList] 404 – ressource introuvable (souvent pseudo AniList inconnu).")
                    return None
                # 5xx / surcharge : souvent temporaire côté AniList — retenter (évite 12× WARNING au boot)
                if resp.status_code in (408, 425, 500, 502, 503, 504) and attempt < max_tries:
                    LOG.debug(
                        "[AniList] HTTP %s (essai %s/%s), nouvel essai dans %.1fs — %s",
                        resp.status_code,
                        attempt,
                        max_tries,
                        backoff,
                        str(j)[:160] if j else resp.text[:160],
                    )
                    time.sleep(backoff)
                    backoff *= 1.8
                    continue
                LOG.warning(
                    "[AniList] HTTP %s (définitif) – %s",
                    resp.status_code,
                    (resp.text[:400] if resp.text else ""),
                )
                return None

            # erreurs GraphQL
            if "errors" in j and j["errors"]:
                LOG.warning("[AniList] GraphQL errors: %s", str(j["errors"])[:300])
                return j

            # OK
            return j

        except Exception as e:
            LOG.warning("[AniList] requête échouée (tentative %s/%s): %s", attempt, max_tries, e)
            if attempt < max_tries:
                time.sleep(backoff)
                backoff *= 1.8
                continue
            return {}

    # si on sort de la boucle sans avoir retourné
    return {}

def load_cached_titles() -> List[dict]:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def get_upcoming_episodes(username: str, *, force: bool = False) -> list[dict]:
    """
    Prochains épisodes pour les entrées AniList **En cours** + **En relecture** (CURRENT, REPEATING).
    Ne retient que les médias où AniList expose `nextAiringEpisode` (épisode annoncé).
    """
    uname = (username or "").strip()
    if not uname:
        return []
    key = uname.lower()
    if not force and _fresh("upcoming", key):
        return _ANILIST_CACHE["upcoming"][key]["data"]

    q = """
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME, status_in: [CURRENT, REPEATING]) {
        lists {
          entries {
            media {
              id
              title { romaji english native }
              siteUrl
              coverImage { large extraLarge }
              genres
              nextAiringEpisode { episode airingAt }
            }
          }
        }
      }
    }"""
    data = query_anilist(q, variables={"name": uname})

    def _stale_or_empty() -> list[dict]:
        """Ne pas renvoyer [] après erreur réseau si on a encore un cache (évite 6h de faux vide)."""
        if force:
            return []
        ent = _ANILIST_CACHE["upcoming"].get(key)
        if ent:
            LOG.debug(
                "[AniList] get_upcoming_episodes: cache antérieur conservé (API indisponible / erreur) — %s",
                uname,
            )
            return list(ent["data"])
        return []

    if not data:
        return _stale_or_empty()

    if isinstance(data, dict) and data.get("errors"):
        inner = data.get("data")
        if inner is None or (isinstance(inner, dict) and inner.get("MediaListCollection") is None):
            LOG.warning(
                "[AniList] get_upcoming_episodes GraphQL erreurs pour %s — %s",
                uname,
                str(data.get("errors"))[:280],
            )
            return _stale_or_empty()

    coll = (data.get("data") or {}).get("MediaListCollection")
    res = []
    if coll:
        for lst in coll.get("lists") or []:
            for e in lst.get("entries") or []:
                m = e.get("media") or {}
                nae = m.get("nextAiringEpisode")
                if nae:
                    cover = (m.get("coverImage") or {})
                    res.append({
                        "id": m.get("id"),
                        "title": m.get("title"),
                        "siteUrl": m.get("siteUrl"),
                        "cover": cover.get("extraLarge") or cover.get("large"),
                        "genres": m.get("genres") or [],
                        "episode": nae.get("episode"),
                        "airingAt": nae.get("airingAt"),
                    })
    res.sort(key=lambda x: x["airingAt"])
    _ANILIST_CACHE["upcoming"][key] = {"ts": time.time(), "data": res}
    return res


def invalidate_upcoming_cache(username: str | None = None) -> None:
    """Vide le cache « upcoming » pour un pseudo (ou tout le bucket si username vide)."""
    if not username or not str(username).strip():
        _ANILIST_CACHE["upcoming"].clear()
        return
    _ANILIST_CACHE["upcoming"].pop(str(username).strip().lower(), None)


def _flatten_media_list_collection(data: dict | None) -> list[dict]:
    """Extrait les médias uniques depuis une réponse MediaListCollection."""
    if not data:
        return []
    coll = (data.get("data") or {}).get("MediaListCollection")
    if not coll:
        return []
    out: list[dict] = []
    seen_ids: set[int] = set()
    for lst in coll.get("lists") or []:
        for e in lst.get("entries") or []:
            m = e.get("media") or {}
            mid = m.get("id")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                out.append(m)
    return out


def fetch_user_list_media_for_minigames(username: str) -> list[dict]:
    """
    Animés présents sur la liste AniList du pseudo (complété, en cours, relecture, en pause).
    Champs utiles aux mini-jeux liés : genres, startDate, episodes, etc.
    """
    uname = (username or "").strip()
    if not uname:
        return []
    q = """
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME, status_in: [COMPLETED, CURRENT, REPEATING, PAUSED]) {
        lists {
          entries {
            media {
              id
              title { romaji english native }
              genres
              startDate { year }
              episodes
              coverImage { extraLarge large }
            }
          }
        }
      }
    }"""
    data = query_anilist(q, variables={"name": uname})
    if not data or "data" not in data:
        return []
    if isinstance(data, dict) and data.get("errors"):
        inner = data.get("data")
        if inner is None or (isinstance(inner, dict) and inner.get("MediaListCollection") is None):
            LOG.debug(
                "[AniList] fetch_user_list_media_for_minigames GraphQL pour %s — %s",
                uname,
                str(data.get("errors"))[:200],
            )
            return []
    return _flatten_media_list_collection(data)


def pick_random_media_for_guess_genre_from_list(media_list: list[dict]) -> Optional[dict]:
    """Choisit un média avec au moins un genre ; None si impossible."""
    if not media_list:
        return None
    with_genres = [m for m in media_list if len(m.get("genres") or []) >= 1]
    if not with_genres:
        return None
    return random.choice(with_genres)


def pick_random_media_for_guess_year_from_list(media_list: list[dict]) -> Optional[dict]:
    """Média avec année de diffusion connue (startDate.year)."""
    if not media_list:
        return None
    with_year = [m for m in media_list if (m.get("startDate") or {}).get("year")]
    if not with_year:
        return None
    return random.choice(with_year)


def pick_random_media_for_guess_episodes_from_list(media_list: list[dict]) -> Optional[dict]:
    """Média avec nombre d'épisodes fixe (int) côté AniList."""
    if not media_list:
        return None
    with_eps = [m for m in media_list if isinstance(m.get("episodes"), int)]
    if not with_eps:
        return None
    return random.choice(with_eps)


def build_guesswho_from_user_list(username: str, *, max_attempts: int = 16) -> Optional[dict]:
    """
    Un personnage (nom + image + indice titre anime) depuis un animé de la liste.
    None si liste vide ou aucun personnage exploitable après essais.
    """
    ml = fetch_user_list_media_for_minigames(username)
    if not ml:
        return None
    rng = random.Random()
    mids = list(ml)
    rng.shuffle(mids)
    for m in mids[:max_attempts]:
        ch = fetch_one_character_from_media(int(m["id"]))
        if ch:
            return {
                "name": ch["name_full"],
                "image_url": ch["image_url"],
                "hint_anime": ch["media_romaji"],
            }
    return None


def fetch_one_character_from_media(media_id: int) -> Optional[dict]:
    """
    Un personnage (nom + image + titre romaji) pour un média.
    None si pas de personnage avec image exploitable.
    """
    q = """
    query ($id: Int) {
      Media(id: $id) {
        title { romaji }
        characters(perPage: 40, sort: [ROLE, FAVOURITES_DESC]) {
          edges {
            node {
              name { full }
              image { large }
            }
          }
        }
      }
    }"""
    data = query_anilist(q, variables={"id": int(media_id)})
    if not data or "data" not in data:
        return None
    media = (data.get("data") or {}).get("Media") or {}
    if not media:
        return None
    title_romaji = (media.get("title") or {}).get("romaji") or "—"
    edges = ((media.get("characters") or {}).get("edges") or [])
    candidates: list[dict] = []
    for e in edges:
        node = e.get("node") or {}
        name = (node.get("name") or {}).get("full")
        img = (node.get("image") or {}).get("large")
        if name and img:
            candidates.append({"name_full": name, "image_url": img, "media_romaji": title_romaji})
    if not candidates:
        return None
    return random.choice(candidates)


def build_guess_character_from_user_list(username: str, *, max_attempts: int = 8) -> Optional[dict]:
    """
    4 noms distincts + index correct + image du bon perso + titre anime source.
    None si moins de 4 entrées listées ou échec après plusieurs tirages.
    """
    media_list = fetch_user_list_media_for_minigames(username)
    if len(media_list) < 4:
        return None
    rng = random.Random()
    for _ in range(max_attempts):
        sampled = rng.sample(media_list, 4)
        chars: list[dict] = []
        ok = True
        for m in sampled:
            ch = fetch_one_character_from_media(int(m["id"]))
            if ch is None:
                ok = False
                break
            chars.append(ch)
        if not ok or len(chars) != 4:
            continue
        names = [c["name_full"] for c in chars]
        if len(set(names)) < 4:
            continue
        correct_idx = rng.randrange(4)
        correct = chars[correct_idx]
        return {
            "options": names,
            "correct_index": correct_idx,
            "correct_name": correct["name_full"],
            "correct_anime": correct["media_romaji"],
            "image_url": correct["image_url"],
        }
    return None


def get_anime_details(media_id: int) -> Optional[dict]:
    query = '''
    query ($id: Int) {
      Media(id: $id) {
        id
        title { romaji english native }
        description
        coverImage { large }
        bannerImage
        format
        episodes
        duration
        status
        season
        seasonYear
        genres
        tags { name }
        averageScore
        popularity
        studios { nodes { name } }
      }
    }
    '''
    try:
        data = query_anilist(query, {"id": media_id})
        return data["data"]["Media"] if data and "data" in data else None
    except Exception as e:
        logger.error(f"Erreur récupération détails anime: {e}")
        return None

@lru_cache(maxsize=100)
def get_character_details(char_id: int) -> Optional[dict]:
    query = '''
    query ($id: Int) {
      Character(id: $id) {
        name { full native }
        image { large }
        description
        gender
        dateOfBirth { month day }
        age
        media { nodes { title { romaji } type } }
      }
    }
    '''
    try:
        data = query_anilist(query, {"id": char_id})
        return data["data"]["Character"] if data and "data" in data else None
    except Exception as e:
        logger.error(f"Erreur récupération personnage: {e}")
        return None

def get_next_airing_one() -> Optional[Dict[str, Any]]:
    query = """
    query {
      Page(perPage: 1){
        airingSchedules(notYetAired:true, sort: TIME){
          airingAt
          episode
          media{
            id
            title{ romaji english native }
            coverImage{ extraLarge large }
            genres
          }
        }
      }
    }
    """
    data = query_anilist(query, variables=None)
    schedules = (data or {}).get("data", {}).get("Page", {}).get("airingSchedules", []) or []
    if not schedules:
        return None
    s = schedules[0]
    m = s.get("media") or {}
    t = m.get("title") or {}
    return {
        "airingAt": s.get("airingAt"),
        "episode": s.get("episode"),
        "title_romaji": t.get("romaji"),
        "title_english": t.get("english"),
        "title_native": t.get("native"),
        "cover": ((m.get("coverImage") or {}).get("extraLarge")
                  or (m.get("coverImage") or {}).get("large")),
        "genres": m.get("genres") or [],
    }

def get_next_airing_for_title(title: str):
    query = '''
    query ($search: String) {
      Media(type: ANIME, search: $search) {
        title { romaji english native }
        nextAiringEpisode { episode airingAt }
        coverImage { large extraLarge }
        format
        season
        seasonYear
      }
    }
    '''
    try:
        result = query_anilist(query, {"search": title}) or {}
        data = result.get("data") or {}
        media = data.get("Media")
        if not media:
            return None
        nae = media.get("nextAiringEpisode")
        if not nae:
            return None
        cover = (media.get("coverImage") or {})
        return {
            "title_romaji": (media.get("title") or {}).get("romaji"),
            "title_english": (media.get("title") or {}).get("english"),
            "title_native": (media.get("title") or {}).get("native"),
            "episode": nae.get("episode"),
            "airingAt": nae.get("airingAt"),
            "cover": cover.get("extraLarge") or cover.get("large"),
            "format": media.get("format"),
            "season": media.get("season"),
            "seasonYear": media.get("seasonYear")
        }
    except Exception as e:
        LOG.error(f"Erreur get_next_airing_for_title({title}): {e}")
        return None

def get_my_next_airing_one() -> Optional[Dict[str, Any]]:
    """Prochain épisode à sortir pour ANILIST_USERNAME (CURRENT)."""
    username = os.getenv("ANILIST_USERNAME") or ANILIST_USERNAME
    if not username:
        return None
    query = """
    query ($userName:String, $page:Int, $perPage:Int){
      Page(page:$page, perPage:$perPage){
        pageInfo{ hasNextPage }
        mediaList(userName:$userName, status:CURRENT, type:ANIME){
          media{
            id
            title{ romaji english native }
            coverImage{ extraLarge large }
            genres
            nextAiringEpisode{ airingAt episode }
          }
        }
      }
    }
    """
    page = 1
    per_page = 50
    now = int(datetime.now(timezone.utc).timestamp())
    best: Optional[Dict[str, Any]] = None
    while True:
        data = query_anilist(query, variables={"userName": username, "page": page, "perPage": per_page})
        page_data = (data or {}).get("data", {}).get("Page", {}) or {}
        entries = page_data.get("mediaList", []) or []
        for e in entries:
            m = e.get("media") or {}
            nae = m.get("nextAiringEpisode") or {}
            airing = nae.get("airingAt")
            if not airing or airing < now:
                continue
            t = m.get("title") or {}
            item = {
                "airingAt": airing,
                "episode": nae.get("episode"),
                "title_romaji": t.get("romaji"),
                "title_english": t.get("english"),
                "title_native": t.get("native"),
                "cover": ((m.get("coverImage") or {}).get("extraLarge")
                          or (m.get("coverImage") or {}).get("large")),
                "genres": m.get("genres") or [],
            }
            if best is None or airing < best["airingAt"]:
                best = item
        if not (page_data.get("pageInfo") or {}).get("hasNextPage"):
            break
        page += 1
    return best

def get_user_next_airing_one(username: str):
    """Prochain épisode à venir pour un utilisateur AniList (dans CURRENT)."""
    query = """
    query ($userName: String) {
      MediaListCollection(userName: $userName, type: ANIME, status_in: [CURRENT]) {
        lists {
          entries {
            media {
              title { romaji english native }
              coverImage { large }
              genres
              nextAiringEpisode { episode airingAt }
            }
          }
        }
      }
    }
    """
    data = query_anilist(query, {"userName": username}) or {}
    coll = (data.get("data") or {}).get("MediaListCollection", {}) or {}
    entries = []
    for lst in coll.get("lists", []) or []:
        for entry in lst.get("entries", []) or []:
            media = entry.get("media") or {}
            if media.get("nextAiringEpisode"):
                entries.append(media)
    if not entries:
        return None
    entries.sort(key=lambda m: m["nextAiringEpisode"]["airingAt"])
    m = entries[0]
    return {
        "title_romaji": (m.get("title") or {}).get("romaji"),
        "title_english": (m.get("title") or {}).get("english"),
        "title_native": (m.get("title") or {}).get("native"),
        "cover": (m.get("coverImage") or {}).get("large"),
        "episode": (m.get("nextAiringEpisode") or {}).get("episode"),
        "airingAt": (m.get("nextAiringEpisode") or {}).get("airingAt"),
        "genres": m.get("genres", [])
    }

# --- Helpers reset mensuel quiz ---

def _month_key(dt: datetime | None = None, tz_name: str = "Europe/Paris") -> str:
    tz = ZoneInfo(tz_name)
    d = dt.astimezone(tz) if isinstance(dt, datetime) else datetime.now(tz)
    return f"{d.year:04d}-{d.month:02d}"

def _prev_month_key(dt: datetime | None = None, tz_name: str = "Europe/Paris") -> str:
    tz = ZoneInfo(tz_name)
    d = dt.astimezone(tz) if isinstance(dt, datetime) else datetime.now(tz)
    year = d.year
    month = d.month - 1
    if month == 0:
        month = 12
        year -= 1
    return f"{year:04d}-{month:02d}"

def human_month_fr(year_month: str) -> str:
    """
    '2025-09' -> 'septembre 2025'
    """
    months = ["janvier","février","mars","avril","mai","juin",
              "juillet","août","septembre","octobre","novembre","décembre"]
    y, m = year_month.split("-")
    m_idx = max(1, min(12, int(m)))
    return f"{months[m_idx-1]} {y}"

def load_winner() -> dict:
    return load_json(FileConfig.WINNER, {})

def save_winner(data: dict) -> None:
    save_json(FileConfig.WINNER, data or {})

def compute_quiz_top(scores: dict, n: int = 10) -> list[tuple[str,int]]:
    """
    Retourne top n sous forme [(user_id_str, score_int), ...] trié desc.
    """
    items = []
    for uid, val in (scores or {}).items():
        try:
            items.append((str(uid), int(val)))
        except Exception:
            continue
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:n]

# Récompenses podium mensuel (classement quiz) : XP global + compteurs badges (mini:quiz_month_*)
QUIZ_MONTHLY_XP_BY_RANK = {1: 600, 2: 350, 3: 200}


def record_month_winner_and_reset(now: datetime | None = None, tz_name: str = "Europe/Paris") -> dict:
    """
    Fige le top 3 du mois précédent dans FileConfig.WINNER puis remet les scores à zéro.
    Retourne le dict sauvegardé (récompenses XP/badges via grant_quiz_monthly_podium_rewards).
    """
    with DATA_JSON_LOCK:
        scores = load_scores()
        prev_m = _prev_month_key(now, tz_name)
        ts = int(time.time())

        if not scores:
            save_scores({})
            data = {
                "month": prev_m,
                "winner_user_id": None,
                "winner_score": 0,
                "podium": [],
                "saved_at": ts,
            }
            save_winner(data)
            return data

        top3 = compute_quiz_top(scores, n=3)
        podium = [{"rank": i, "user_id": uid, "score": int(sc)} for i, (uid, sc) in enumerate(top3, start=1)]
        best_uid = top3[0][0] if top3 else None
        best_score = int(top3[0][1]) if top3 else 0

        data = {
            "month": prev_m,
            "winner_user_id": best_uid,
            "winner_score": best_score,
            "podium": podium,
            "saved_at": ts,
        }
        save_winner(data)
        save_scores({})
        return data


async def grant_quiz_monthly_podium_rewards(bot, data: dict | None) -> None:
    """
    Après record_month_winner_and_reset : XP global + progression trophées podium.
    Envoie un MP si possible (MP fermés ignorés).
    """
    if not data:
        return
    podium = data.get("podium") or []
    month_key = data.get("month") or "?"
    month_fr = human_month_fr(month_key) if month_key and month_key != "?" else month_key
    mini_keys = {1: "quiz_month_1st", 2: "quiz_month_2nd", 3: "quiz_month_3rd"}

    for row in podium:
        try:
            rank = int(row.get("rank") or 0)
            uid_s = row.get("user_id")
            sc = int(row.get("score") or 0)
            if not uid_s or rank not in (1, 2, 3):
                continue
            uid_int = int(uid_s)
        except Exception:
            continue

        xp_amt = int(QUIZ_MONTHLY_XP_BY_RANK.get(rank, 0))
        if xp_amt > 0:
            try:
                await add_xp(bot, None, uid_int, xp_amt, announce=False)
            except Exception as e:
                LOG.warning("grant_quiz_monthly_podium_rewards add_xp uid=%s: %s", uid_int, e)

        mk = mini_keys.get(rank)
        if mk:
            try:
                add_mini_score(uid_int, mk, 1)
            except Exception as e:
                LOG.warning("grant_quiz_monthly_podium_rewards mini uid=%s: %s", uid_int, e)

        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "🏅")
        try:
            u = await bot.fetch_user(uid_int)
            await u.send(
                f"{medal} **Classement quiz — {month_fr}**\n"
                f"Tu es **{rank}ᵉ** avec **{sc}** pts ce mois-là.\n"
                f"**+{xp_amt} XP** (rang global / **/mycard**) et progression trophée **/mybadges**."
            )
        except Exception:
            pass

    if podium:
        LOG.info(
            "Quiz mensuel %s : récompenses podium envoyées (%d joueur(s)).",
            month_key,
            len(podium),
        )

# ---- Stats profil (User.statistics) ----
def get_anilist_stats(username: str) -> Optional[Dict[str, Any]]:
    """
    Stats de profil AniList (User.statistics.anime):
    Retourne {count, minutesWatched, meanScore, favoriteGenre}
    """
    query = """
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
    """
    data = query_anilist(query, {"name": username}) or {}
    user = (data.get("data") or {}).get("User") or None
    if not user:
        return None
    anim = (user.get("statistics") or {}).get("anime") or {}
    genres = anim.get("genres") or []
    fav_genre = None
    if genres:
        fav_genre = max(genres, key=lambda g: g.get("count", 0)).get("genre")
    return {
        "count": anim.get("count", 0),
        "minutesWatched": anim.get("minutesWatched", 0),
        "meanScore": anim.get("meanScore", 0),
        "favoriteGenre": fav_genre or "—",
    }

# ---- Stats liste (totaux completed/current/total) ----
def fetch_anilist_list_stats(username: str) -> dict:
    """
    Via MediaListCollection: {total_entries, completed, current}
    """
    query = """
    query($userName:String){
      MediaListCollection(userName:$userName, type: ANIME){
        lists { entries { status } }
      }
    }
    """
    try:
        data = query_anilist(query, {"userName": username}) or {}
        lists = (data.get("data") or {}).get("MediaListCollection", {}).get("lists", []) or []
        total_entries = sum(len(l.get("entries", [])) for l in lists)
        completed = sum(
            1 for l in lists for e in l.get("entries", [])
            if str(e.get("status","")).upper() == "COMPLETED"
        )
        current = sum(
            1 for l in lists for e in l.get("entries", [])
            if str(e.get("status","")).upper() == "CURRENT"
        )
        return {"total_entries": total_entries, "completed": completed, "current": current}
    except Exception:
        return {}

# ---- Shims pour compat avec les cogs "sync" / "mystats" récents ----
def get_or_refresh_anilist_stats(username: str, ttl_hours: int = 12) -> dict:
    # Pas de cache “ancien” -> on renvoie direct la valeur live
    return fetch_anilist_list_stats(username)

def force_refresh_anilist_stats(username: str) -> dict:
    return fetch_anilist_list_stats(username)

def get_or_refresh_anilist_profile(username: str, ttl_hours: int = 12) -> dict:
    return get_anilist_stats(username) or {}

def force_refresh_anilist_profile(username: str) -> dict:
    return get_anilist_stats(username) or {}

# ================= MINI-JEUX =================
def load_mini_scores() -> dict:
    return load_json(FileConfig.MINI_SCORES, {})

def save_mini_scores(data: dict) -> None:
    save_json(FileConfig.MINI_SCORES, data)

def add_mini_score(user_id: int, game: str, amount: int = 1) -> None:
    with DATA_JSON_LOCK:
        data = load_mini_scores()
        uid = str(user_id)
        data.setdefault(uid, {})
        data[uid][game] = data[uid].get(game, 0) + amount
        save_mini_scores(data)

def get_mini_scores(user_id: int) -> dict:
    data = load_mini_scores()
    return data.get(str(user_id), {})


def mini_game_leaderboard(game: str, n: int = 10) -> list[tuple[int, int]]:
    """Top `n` joueurs pour un mini-jeu (`mini_scores.json`, compteur du jeu)."""
    g = (game or "").strip().lower()
    if not g:
        return []
    data = load_mini_scores()
    rows: list[tuple[int, int]] = []
    for uid_str, games in (data or {}).items():
        try:
            uid = int(uid_str)
        except Exception:
            continue
        v = int((games or {}).get(g, 0))
        if v > 0:
            rows.append((uid, v))
    rows.sort(key=lambda x: (-x[1], x[0]))
    return rows[: max(1, int(n))]


def mini_game_activity_leaderboard(*, n: int = 10) -> list[tuple[int, int]]:
    """Top `n` par somme de toutes les entrées mini-jeux (activité globale)."""
    data = load_mini_scores()
    totals: dict[int, int] = {}
    for uid_str, games in (data or {}).items():
        try:
            uid = int(uid_str)
        except Exception:
            continue
        s = 0
        for v in (games or {}).values():
            try:
                s += int(v)
            except Exception:
                pass
        if s > 0:
            totals[uid] = s
    rows = sorted(totals.items(), key=lambda x: (-x[1], x[0]))
    return rows[: max(1, int(n))]


def get_guess_genre_penalty_count(user_id: int) -> int:
    """Nombre de pénalités anti-spam /guess genre enregistrées (affichage mycard)."""
    data = load_json(FileConfig.GUESS_GENRE_SANCTIONS, {})
    return int(data.get(str(user_id), {}).get("penalties", 0))


def inc_guess_genre_penalty_count(user_id: int) -> int:
    """Incrémente le compteur persistant de pénalités guess-genre."""
    data = load_json(FileConfig.GUESS_GENRE_SANCTIONS, {})
    uid = str(user_id)
    ent = data.get(uid, {"penalties": 0})
    ent["penalties"] = int(ent.get("penalties", 0)) + 1
    data[uid] = ent
    save_json(FileConfig.GUESS_GENRE_SANCTIONS, data)
    return int(ent["penalties"])


# ================= LIENS / PREFS / TRACKER =================
def load_links() -> dict:
    return load_json(FileConfig.LINKED_USERS, {})

def save_links(data: dict) -> None:
    save_json(FileConfig.LINKED_USERS, data)

def get_user_anilist(user_id: int) -> Optional[str]:
    """Pseudo AniList lié (SQLite d’abord, puis JSON legacy)."""
    u = get_linked_username(user_id)
    if u:
        return u
    v = (load_links() or {}).get(str(user_id))
    return _coerce_anilist_username(v) if v else None


def set_linked_username(user_id: int, username: str) -> None:
    uid = int(user_id)
    uname = (username or "").strip()
    if not uname:
        raise ValueError("empty_username")
    taken = discord_id_for_linked_anilist_username(uname)
    if taken is not None and taken != uid:
        raise ValueError("anilist_username_taken")
    with _db_conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO anilist_links (discord_id, username, linked_at) "
            "VALUES (?, ?, strftime('%s','now'))",
            (uid, uname)
        )

def get_linked_username(user_id: int) -> str | None:
    with _db_conn() as con:
        row = con.execute(
            "SELECT username FROM anilist_links WHERE discord_id = ?",
            (int(user_id),)
        ).fetchone()
        return row[0] if row else None


def discord_id_for_linked_anilist_username(username: str) -> int | None:
    """ID Discord déjà associé à ce pseudo AniList (casse ignorée), ou None."""
    key = (username or "").strip().lower()
    if not key:
        return None
    try:
        with _db_conn() as con:
            row = con.execute(
                "SELECT discord_id FROM anilist_links WHERE lower(username) = ?",
                (key,),
            ).fetchone()
            return int(row[0]) if row else None
    except Exception:
        return None


def _ensure_anilist_link_pending_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS anilist_link_pending (
            discord_id INTEGER PRIMARY KEY,
            username   TEXT NOT NULL,
            token      TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )


def anilist_set_link_pending(discord_id: int, username: str, token: str) -> None:
    import time as _time

    uid = int(discord_id)
    with _db_conn() as con:
        _ensure_anilist_link_pending_table(con)
        con.execute(
            "INSERT OR REPLACE INTO anilist_link_pending (discord_id, username, token, created_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, (username or "").strip(), (token or "").strip(), int(_time.time())),
        )


def anilist_get_link_pending(discord_id: int) -> tuple[str, str, int] | None:
    uid = int(discord_id)
    try:
        with _db_conn() as con:
            _ensure_anilist_link_pending_table(con)
            row = con.execute(
                "SELECT username, token, created_at FROM anilist_link_pending WHERE discord_id = ?",
                (uid,),
            ).fetchone()
            if not row:
                return None
            return str(row[0]), str(row[1]), int(row[2])
    except Exception:
        return None


def anilist_clear_link_pending(discord_id: int) -> None:
    uid = int(discord_id)
    try:
        with _db_conn() as con:
            _ensure_anilist_link_pending_table(con)
            con.execute("DELETE FROM anilist_link_pending WHERE discord_id = ?", (uid,))
    except Exception:
        pass


def fetch_anilist_user_about(username: str) -> str | None:
    """Texte « À propos » public du profil AniList (pour vérif de lien)."""
    name = _normalize_name(username or "")
    if not name:
        return None
    q = "query ($name: String){ User(name: $name) { about } }"
    try:
        data = query_anilist(q, {"name": name})
        u = (data or {}).get("data", {}).get("User") if isinstance(data, dict) else None
        if not u:
            return None
        ab = u.get("about")
        return str(ab) if ab is not None else ""
    except Exception:
        return None


def record_owner_slash_command(qualified_name: str) -> None:
    """Comptage anonyme des usages slash (mois courant + mois précédent archivé)."""
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    path = FileConfig.OWNER_TELEMETRY
    data = load_json(path, {})
    cur_m = data.get("current_month")
    if cur_m != month:
        if cur_m and data.get("current"):
            data["previous_month"] = cur_m
            data["previous"] = data.get("current")
        data["current_month"] = month
        data["current"] = {"commands": {}, "peak_guilds": 0, "peak_members": 0}
    cur = data.setdefault("current", {})
    cmds = cur.setdefault("commands", {})
    qn = (qualified_name or "?").lower()
    cmds[qn] = cmds.get(qn, 0) + 1
    save_json(path, data)


def owner_telemetry_refresh_peaks(bot: discord.Client) -> None:
    """Met à jour les pics serveurs / membres pour le mois déjà initialisé (voir comptage slash)."""
    try:
        path = FileConfig.OWNER_TELEMETRY
        data = load_json(path, {})
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        if data.get("current_month") != month:
            return
        cur = data.setdefault("current", {})
        guild_n = len(getattr(bot, "guilds", []) or [])
        member_n = sum((g.member_count or 0) for g in (getattr(bot, "guilds", []) or []))
        cur["peak_guilds"] = max(int(cur.get("peak_guilds", 0)), guild_n)
        cur["peak_members"] = max(int(cur.get("peak_members", 0)), member_n)
        save_json(path, data)
    except Exception:
        pass


def owner_telemetry_summary() -> dict[str, Any]:
    """Charge owner_telemetry.json pour affichage admin (sans dépendre de Discord)."""
    return load_json(FileConfig.OWNER_TELEMETRY, {})


def iter_discord_anilist_links() -> List[Tuple[int, str]]:
    """Couples (discord_id, pseudo AniList) : SQLite + JSON legacy (SQLite écrase le JSON si même id)."""
    merged: dict[int, str] = {}
    try:
        for uid_str, v in (load_links() or {}).items():
            try:
                uid = int(uid_str)
                u = _coerce_anilist_username(v)
                if u:
                    merged[uid] = u
            except Exception:
                pass
    except Exception:
        pass
    try:
        with _db_conn() as con:
            for row in con.execute("SELECT discord_id, username FROM anilist_links"):
                merged[int(row[0])] = str(row[1])
    except Exception:
        pass
    return list(merged.items())


def unlink_linked_username(user_id: int) -> bool:
    """Supprime le lien AniList (SQLite + fichier JSON legacy). Retourne True si quelque chose a été retiré."""
    uid = int(user_id)
    removed = False
    with _db_conn() as con:
        cur = con.execute("DELETE FROM anilist_links WHERE discord_id = ?", (uid,))
        if cur.rowcount and cur.rowcount > 0:
            removed = True
    try:
        data = load_links()
        key = str(uid)
        if key in data:
            del data[key]
            save_links(data)
            removed = True
    except Exception:
        pass
    return removed


def format_anilist_title_obj(title: Any) -> str:
    """Affiche un titre AniList (dict {romaji, english, native} ou str)."""
    if isinstance(title, dict):
        return (
            title.get("romaji")
            or title.get("english")
            or title.get("native")
            or "Titre inconnu"
        )
    return str(title or "Titre inconnu")


def format_anilist_episode_title_markdown(ep: dict) -> str:
    """
    Titre d’épisode en markdown pour embed (lien AniList si id ou siteUrl présent).
    Les ] dans le titre sont neutralisés pour ne pas casser le lien markdown.
    """
    t = format_anilist_title_obj(ep.get("title"))
    url = (ep.get("siteUrl") or "").strip()
    if not url:
        mid = ep.get("id")
        if mid is not None:
            try:
                url = f"https://anilist.co/anime/{int(mid)}"
            except (TypeError, ValueError):
                url = ""
    if not url:
        return f"**{t}**"
    safe = t.replace("]", "›")
    return f"[**{safe}**]({url})"


# --- LINKS ---
def link_anilist(user_id: int, username: str, anilist_id: int) -> None:
    conn = _db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anilist_links (
            user_id     INTEGER PRIMARY KEY,
            anilist_id  INTEGER NOT NULL,
            username    TEXT    NOT NULL
        )
    """)
    conn.execute("INSERT OR REPLACE INTO anilist_links (user_id, anilist_id, username) VALUES (?,?,?)",
                 (user_id, anilist_id, username))
    conn.commit()

def get_linked_anilist(user_id: int) -> dict | None:
    conn = _db()
    row = conn.execute("SELECT anilist_id, username FROM anilist_links WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1]}

# --- STATS CACHE ---
def _ensure_stats_table():
    conn = _db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anilist_stats (
            user_id        INTEGER PRIMARY KEY,
            completed      INTEGER,
            current        INTEGER,
            total_entries  INTEGER,
            watched_count  INTEGER,
            avg_score      REAL,
            top_genre      TEXT,
            updated_at     INTEGER
        )
    """)
    conn.commit()

def save_stats_cache(user_id: int, stats: dict) -> None:
    import time
    _ensure_stats_table()
    conn = _db()
    conn.execute("""
        INSERT OR REPLACE INTO anilist_stats
        (user_id, completed, current, total_entries, watched_count, avg_score, top_genre, updated_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        user_id,
        stats.get("completed", 0),
        stats.get("current", 0),
        stats.get("total_entries", 0),
        stats.get("watched_count", 0),
        stats.get("avg_score", 0.0),
        stats.get("top_genre") or None,
        int(time.time()),
    ))
    conn.commit()

def get_stats_cache(user_id: int) -> dict | None:
    _ensure_stats_table()
    conn = _db()
    row = conn.execute("SELECT completed,current,total_entries,watched_count,avg_score,top_genre,updated_at FROM anilist_stats WHERE user_id=?", (user_id,)).fetchone()
    if not row: return None
    return {
        "completed": row[0], "current": row[1], "total_entries": row[2],
        "watched_count": row[3], "avg_score": row[4], "top_genre": row[5],
        "updated_at": row[6],
    }

def get_user_stats(user_id: int):
    return get_game_stats(user_id)

def load_preferences() -> dict:
    return load_json(FileConfig.PREFERENCES, {})

def save_preferences(data: dict) -> None:
    save_json(FileConfig.PREFERENCES, data)

def load_user_settings() -> dict:
    return load_json(FileConfig.USER_SETTINGS, {})

def save_user_settings(settings: dict) -> None:
    save_json(FileConfig.USER_SETTINGS, settings)


def get_mission_dm_notify(user_id: int) -> bool:
    """MP quand une mission se termine via événement (hors salon). Défaut : True."""
    st = (load_user_settings() or {}).get(str(user_id), {}) or {}
    return bool(st.get("mission_dm_notify", True))


def set_mission_dm_notify(user_id: int, enabled: bool) -> None:
    data = load_user_settings() or {}
    uid = str(user_id)
    data.setdefault(uid, {})
    data[uid]["mission_dm_notify"] = bool(enabled)
    save_user_settings(data)


def load_tracker() -> dict:
    return load_json(FileConfig.TRACKER, {})

def save_tracker(data: dict) -> None:
    save_json(FileConfig.TRACKER, data)

# ================= TITRES / SIMILARITÉ =================
def normalize(text: str | None) -> str:
    if not text:
        return ""
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return ''.join(e for e in text.lower() if e.isalnum() or e.isspace()).strip()

def normalize_title(title: str) -> str:
    title = normalize(title)
    stop_words = {"the", "a", "an", "season", "part", "episode", "movie", "saison"}
    words = [w for w in title.split() if w not in stop_words]
    clean = re.sub(r"(s\d|season \d|part \d|[^\w\s])", "", " ".join(words), flags=re.IGNORECASE)
    return clean.strip()

def find_similar_titles(query: str, threshold: float = 0.85) -> List[str]:
    query = normalize_title(query)
    if not query:
        return []
    cache = load_json(FileConfig.TITLE_CACHE, [])
    matches: List[str] = []
    for title in cache:
        if not title:
            continue
        if query == title or (
            len(query) >= 2 and (query in title or title in query)
        ):
            matches.append(title)
            continue
        if difflib.SequenceMatcher(None, query, title).ratio() >= threshold:
            matches.append(title)
    return matches

# Petit utilitaire: maj du cache de titres (async pour être "awaitable")
async def update_title_cache() -> int:
    """
    Met à jour FileConfig.TITLE_CACHE avec une liste de titres normalisés.
    Ici on se contente d’un no-op doux si rien n’est branché.
    Retourne le nombre de titres enregistrés.
    """
    # Si tu as un collecteur réel, plug ici. On garde la compat avec bot.update_title_cache().
    existing = load_json(FileConfig.TITLE_CACHE, [])
    save_json(FileConfig.TITLE_CACHE, existing)
    return len(existing)

# ================= IMAGES =================
def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans-{name}.ttf",
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        f"/usr/share/fonts/truetype/liberation2/LiberationSans-{name}.ttf",
        os.path.join(ASSETS_DIR, "fonts", f"DejaVuSans-{name}.ttf"),
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def generate_stats_card(
    user_name: str,
    avatar_url: str | None,
    anime_count: int,
    days_watched: float,
    mean_score: float,
    fav_genre: str,
) -> io.BytesIO:
    width, height = 900, 500
    card = Image.new("RGB", (width, height), color=(25, 25, 35))
    draw = ImageDraw.Draw(card)

    font_title = load_font("Bold", 40)
    font_stats = load_font("Regular", 30)

    if avatar_url:
        try:
            response = requests.get(avatar_url, timeout=10)
            avatar = Image.open(io.BytesIO(response.content)).convert("RGBA")
            size = 150
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            avatar = avatar.resize((size, size))
            card.paste(avatar, (50, 50), mask)
        except Exception as e:
            logger.error(f"Erreur chargement avatar: {e}")

    title_x = 250
    stats_y = 150

    draw.text((title_x, 50), f"Statistiques de {user_name}", font=font_title, fill=(255, 255, 255))
    stats = [
        (f"🎬 Animés vus : {anime_count}", (255, 200, 100)),
        (f"🕒 Temps total : {days_watched:.1f} jours", (100, 200, 255)),
        (f"⭐ Score moyen : {mean_score:.1f}", (255, 100, 100)),
        (f"🎭 Genre favori : {fav_genre}", (200, 255, 100))
    ]
    for i, (text, color) in enumerate(stats):
        draw.text((title_x, stats_y + i * 60), text, font=font_stats, fill=color)

    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf

def format_date_fr(dt: datetime, pattern: str = "EEEE d MMMM") -> str:
    return format_datetime(dt, pattern, locale='fr_FR').capitalize()

# --- remplace ENTIEREMENT ta fonction par ceci ---
def generate_next_image(ep: dict, dt: datetime, tagline: str = "Prochain épisode") -> io.BytesIO:
    """
    Crée une carte type "annonce" :
    - fond : cover floutée
    - bandeau sombre arrondi avec gradient
    - vignette cover
    - titre / épisode / genres / date
    ep attendu: { title, episode, genres(list[str])?, image(url)?, cover(url)? }
    """
    from PIL import ImageFilter, ImageOps

    # ---------- helpers mesures ----------
    def text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
        try:
            return int(draw.textlength(text, font=font))
        except Exception:
            try:
                x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
                return int(x1 - x0)
            except Exception:
                return int(len(text) * font.size * 0.6)

    def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        words = (text or "").split()
        if not words:
            return [""]
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if text_w(draw, t, font) <= max_width:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def round_rect(im: Image.Image, xy: tuple[int,int,int,int], r: int, fill: tuple[int,int,int,int]):
        x0, y0, x1, y1 = xy
        w, h = x1 - x0, y1 - y0
        box = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        mask = Image.new("L", (w, h), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rounded_rectangle((0, 0, w, h), radius=r, fill=255)
        layer = Image.new("RGBA", (w, h), fill)
        box.paste(layer, (0, 0), mask)
        im.paste(box, (x0, y0), mask)

    # ---------- canvas ----------
    W, H = 1024, 420
    card = Image.new("RGBA", (W, H), (20, 18, 24, 255))
    draw = ImageDraw.Draw(card)

    # ---------- fonds / cover ----------
    cover_url = ep.get("image") or ep.get("cover")
    bg = None
    if cover_url:
        try:
            resp = requests.get(cover_url, timeout=10)
            img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            # plein écran + crop
            ratio = img.width / img.height
            target_ratio = W / H
            if ratio > target_ratio:
                nh = H
                nw = int(nh * ratio)
                img = img.resize((nw, nh), Image.LANCZOS)
                left = (nw - W) // 2
                img = img.crop((left, 0, left + W, H))
            else:
                nw = W
                nh = int(nw / ratio)
                img = img.resize((nw, nh), Image.LANCZOS)
                top = (nh - H) // 2
                img = img.crop((0, top, W, top + H))

            # blur + assombrir légèrement
            bg = img.filter(ImageFilter.GaussianBlur(12))
            dim = Image.new("RGBA", (W, H), (0, 0, 0, 110))
            bg = Image.alpha_composite(bg, dim)
        except Exception:
            bg = None

    if bg is None:
        bg = Image.new("RGBA", (W, H), (25, 22, 30, 255))
    card = Image.alpha_composite(bg, card)

    # ---------- bandeau arrondi ----------
    pad = 28
    band_h = H - pad * 2
    band = (pad, pad, W - pad, H - pad)
    round_rect(card, band, r=24, fill=(0, 0, 0, 145))

    # gradient léger à droite
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    for i in range(0, 520):
        a = int(160 * (1 - i / 520))
        gdraw.rectangle((W - i - pad, pad, W - pad, H - pad), fill=(0, 0, 0, max(0, a)))
    card = Image.alpha_composite(card, grad)
    draw = ImageDraw.Draw(card)

    # ---------- mini-cover ----------
    thumb_size = band_h - 24
    x_thumb = pad + 16
    y_thumb = pad + 12
    if cover_url:
        try:
            resp = requests.get(cover_url, timeout=10)
            thumb = Image.open(io.BytesIO(resp.content)).convert("RGBA").resize((thumb_size, thumb_size), Image.LANCZOS)
            # masque arrondi
            mask = Image.new("L", (thumb_size, thumb_size), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, thumb_size, thumb_size), radius=22, fill=255)
            box = Image.new("RGBA", (thumb_size, thumb_size), (0, 0, 0, 0))
            box.paste(thumb, (0, 0), mask)
            card.paste(box, (x_thumb, y_thumb), mask)
        except Exception:
            pass

    # ---------- textes ----------
    # polices
    def load_font_safe(name: str, size: int):
        try:
            return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/DejaVuSans-{name}.ttf", size)
        except Exception:
            try:
                return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
            except Exception:
                return ImageFont.load_default()

    f_title = load_font_safe("Bold", 36)
    f_meta  = load_font_safe("Regular", 22)
    f_tag   = load_font_safe("Regular", 20)

    # zones
    x0 = x_thumb + thumb_size + 22
    y0 = pad + 20
    maxw = W - pad - x0 - 16

    title = ep.get("title") or "Anime"
    lines = wrap(draw, title, f_title, maxw)
    y = y0
    for i, l in enumerate(lines[:2]):  # 2 lignes max pour le titre
        draw.text((x0, y), l, font=f_title, fill=(255, 255, 255, 235))
        y += 40

    # épisode
    epnum = ep.get("episode") or "?"
    draw.text((x0, y), f"Épisode {epnum}", font=f_meta, fill=(255, 215, 130, 255))
    y += 34

    # genres
    genres = ep.get("genres") or []
    if genres:
        g = " • ".join(genres[:4])
        draw.text((x0, y), g, font=f_tag, fill=(220, 220, 220, 210))
        y += 30

    # date
    when = format_date_fr(dt, "EEE d MMM. HH:mm")
    draw.text((x0, y), when, font=f_meta, fill=(220, 220, 220, 235))

    # tag en haut à gauche
    draw.text((pad + 6, pad - 4), tagline, font=f_tag, fill=(130, 235, 160, 240))

    # sortie
    out = io.BytesIO()
    card = card.convert("RGB")
    card.save(out, format="JPEG", quality=92)
    out.seek(0)
    return out


def generate_profile_card(user_name, avatar_url, level, xp, next_xp, quiz_score, mini_scores):
    width, height = 800, 400
    bg = Image.new("RGBA", (width, height), (25, 25, 30))
    draw = ImageDraw.Draw(bg)

    avatar_size = 150
    try:
        response = requests.get(avatar_url, timeout=5)
        avatar = Image.open(BytesIO(response.content)).convert("RGBA").resize((avatar_size, avatar_size))
    except Exception:
        avatar = Image.new("RGBA", (avatar_size, avatar_size), (80, 80, 255))

    mask = Image.new("L", (avatar_size, avatar_size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
    avatar.putalpha(mask)
    bg.paste(avatar, (40, 40), avatar)

    try:
        font_title = ImageFont.truetype("arialbd.ttf", 32)
        font_text  = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_text  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)

    draw.text((220, 40), f"{user_name}", font=font_title, fill=(255, 255, 255))
    draw.text((220, 90), f"Niveau {level} – {xp}/{next_xp} XP", font=font_text, fill=(200, 200, 200))
    draw.text((220, 120), f"🏆 Score Quiz : {quiz_score}", font=font_text, fill=(230, 230, 230))
    draw.text((220, 160), "🎮 Mini-jeux :", font=font_text, fill=(255, 255, 255))

    y = 190
    mapping = {
        "animequiz": "Quiz",
        "higherlower": "Higher/Lower",
        "highermean": "Higher/Mean",
        "guessyear": "Guess Year",
        "guessepisodes": "Guess Episodes",
        "guessgenre": "Guess Genre",
        "guessop": "Guess Opening",
        "guesschar": "Guess Character",
        "duel": "Duel",
    }
    for key, val in (mini_scores or {}).items():
        name = mapping.get(key, key.replace("_", " ").capitalize())
        draw.text((240, y), f"- {name} : {val}", font=font_text, fill=(180, 180, 180))
        y += 28

    buffer = BytesIO()
    bg.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer

# ================= FORMAT / DIVERS =================
def genre_emoji(genres: List[str]) -> str:
    if not genres:
        return "🎬"
    for genre in genres:
        if emoji := GENRE_EMOJIS.get(genre):
            return emoji
    return "🎬"

def get_xp_bar(xp: int, next_xp: int, length: int = 20) -> str:
    next_xp = max(1, int(next_xp))
    filled = int((xp / next_xp) * length)
    filled = max(0, min(length, filled))
    return "▰" * filled + "▱" * (length - filled)

# --- ANTI-DUPLICATE POSTING ---
def _db():
    return _db_conn()


def has_been_posted(media_id: int, ep: int, channel_id: int, kind: str) -> bool:
    conn = _db_conn()
    cur = conn.execute(
        "SELECT 1 FROM posted_events WHERE media_id=? AND episode=? AND channel_id=? AND kind=?",
        (media_id, ep, channel_id, kind)
    )
    return cur.fetchone() is not None

def mark_posted(media_id: int, ep: int, channel_id: int, kind: str) -> None:
    import time
    conn = _db()
    conn.execute(
        "INSERT OR IGNORE INTO posted_events (media_id, episode, channel_id, kind, posted_at) VALUES (?,?,?,?,?)",
        (media_id, ep, channel_id, kind, int(time.time()))
    )
    conn.commit()

# ================= CONFIG BOT / NOTIFS =================
def get_config() -> dict:
    config = load_json(FileConfig.CONFIG, {})
    defaults = {
        "channel_id": None,
        "guild_alert_channels": {},
        "guild_levelup_channels": {},
        "notification_delay": 10,  # minutes
        "daily_summary": True,
        "default_alert_time": "08:00",
    }
    if not config:
        config.update(defaults)
        save_config(config)
    else:
        changed = False
        for k, v in defaults.items():
            if k not in config:
                config[k] = v
                changed = True
        if changed:
            save_config(config)
    return config

def save_config(config: dict) -> None:
    save_json(FileConfig.CONFIG, config)


def get_guild_alert_channel_id(guild_id: int) -> Optional[int]:
    """Salon d’annonces « sortie épisode » pour ce serveur (`/setchannel`)."""
    cfg = get_config()
    m = cfg.get("guild_alert_channels") or {}
    v = m.get(str(int(guild_id)))
    if v is not None and v != "":
        try:
            return int(v)
        except Exception:
            return None
    return None


def set_guild_alert_channel(guild_id: int, channel_id: int) -> None:
    """Enregistre le salon d’annonces « sortie d’épisode » pour ce serveur (ne modifie pas d’ID global multi-serveur)."""
    cfg = get_config()
    cfg.setdefault("guild_alert_channels", {})[str(int(guild_id))] = int(channel_id)
    save_config(cfg)


def get_guild_levelup_channel_id(guild_id: int) -> Optional[int]:
    """Salon des annonces de **montée de niveau XP** (optionnel, `/setlevelupchannel`)."""
    cfg = get_config()
    m = cfg.get("guild_levelup_channels") or {}
    v = m.get(str(int(guild_id)))
    if v is not None and v != "":
        try:
            return int(v)
        except Exception:
            return None
    return None


def set_guild_levelup_channel(guild_id: int, channel_id: int) -> None:
    """Définit le salon où poster les messages « niveau XP augmenté » pour ce serveur."""
    cfg = get_config()
    cfg.setdefault("guild_levelup_channels", {})[str(int(guild_id))] = int(channel_id)
    save_config(cfg)


def clear_guild_levelup_channel(guild_id: int) -> None:
    """Revient au comportement par défaut : annonce dans le salon où l’XP a été gagnée."""
    cfg = get_config()
    m = cfg.get("guild_levelup_channels") or {}
    m.pop(str(int(guild_id)), None)
    cfg["guild_levelup_channels"] = m
    save_config(cfg)


def format_guild_channels_config_summary(bot: discord.Client, guild_id: int) -> str:
    """
    Résumé lisible pour **une seule guilde** (alertes épisodes, montées de niveau, raid boss, legacy local).

    N’expose pas les salons des autres serveurs. Le champ legacy global n’est affiché que si le salon
    résolu appartient à cette guilde (sinon ignoré, pour éviter fuite d’info).
    """
    cfg = get_config()
    lines: list[str] = []
    gid_str = str(int(guild_id))

    ga = cfg.get("guild_alert_channels") or {}
    if gid_str in ga:
        cid = ga[gid_str]
        try:
            ch = bot.get_channel(int(cid))
            mention = getattr(ch, "mention", None) or f"`{cid}`"
        except Exception:
            mention = f"`{cid}`"
        lines.append(f"• **Alertes épisodes** → {mention}")

    gl = cfg.get("guild_levelup_channels") or {}
    if gid_str in gl:
        cid = gl[gid_str]
        try:
            ch = bot.get_channel(int(cid))
            mention = getattr(ch, "mention", None) or f"`{cid}`"
        except Exception:
            mention = f"`{cid}`"
        lines.append(f"• **Titres XP / quiz** → {mention}")

    raid_cfg = load_json(FileConfig.BOSS_RAID, {})
    entry = raid_cfg.get(gid_str)
    if isinstance(entry, dict):
        cid = entry.get("channel_id")
        if cid:
            try:
                ch = bot.get_channel(int(cid))
                mention = getattr(ch, "mention", None) or f"`{cid}`"
            except Exception:
                mention = f"`{cid}`"
            auto = "oui" if entry.get("enabled") else "non"
            lines.append(
                f"• **Raid boss** → {mention} _(lancement auto hebdo : **{auto}**)_"
            )

    leg = cfg.get("channel_id")
    if leg:
        try:
            ch = bot.get_channel(int(leg))
            if isinstance(ch, discord.TextChannel) and ch.guild and ch.guild.id == int(guild_id):
                mention = getattr(ch, "mention", None) or f"`{leg}`"
                lines.append(
                    f"• _(legacy)_ **channel_id** global → {mention} "
                    f"_(ancien réglage ; les alertes utilisent **Alertes épisodes** ci-dessus quand c’est défini)_"
                )
        except Exception:
            pass

    if not lines:
        return (
            "Aucun salon configuré pour **ce serveur** "
            "(`/setchannel`, `/setlevelupchannel`, `/raidconfig`)."
        )
    return "\n".join(lines)


def should_notify(ep: dict) -> bool:
    if not ep.get("airingAt"):
        return False
    now = datetime.now(timezone.utc).timestamp()
    delay = get_config().get("notification_delay", 10) * 60
    return abs(ep["airingAt"] - now) <= delay

# ================= GAME STATS (PROFILE) =================
def get_game_stats(user_id: int) -> dict:
    levels = load_levels()
    scores = load_scores()
    mini_scores = get_mini_scores(user_id)

    user_data = levels.get(str(user_id), {"xp": 0, "level": 0})
    quiz_score = scores.get(str(user_id), 0)

    return {
        "xp": user_data["xp"],
        "level": user_data["level"],
        "next_xp": (user_data["level"] + 1) * 100,
        "quiz_score": quiz_score,
        "mini_scores": mini_scores,
        "title": get_title_for_global_level(user_data["level"]),
        "quiz_title": get_title_for_quiz_score(quiz_score),
    }

def format_mini_game_name(game: str) -> str:
    mapping = {
        "animequiz": "Quiz",
        "higherlower": "Higher/Lower",
        "highermean": "Higher/Mean",
        "guessyear": "Guess Year",
        "guessepisodes": "Guess Episodes",
        "guessgenre": "Guess Genre",
        "guessop": "Guess Opening",
        "guesschar": "Guess Character",
        "duel": "Duel"
    }
    return mapping.get(game, game.replace("_", " ").title())

def get_anilist_stats_for_discord(discord_id: int, fallback_env: bool = True) -> Optional[Dict[str, Any]]:
    username = get_linked_username(discord_id)
    if not username and fallback_env:
        username = ANILIST_USERNAME
    if not username:
        return None
    return get_anilist_stats(username)

def humanize_minutes(total_minutes: int) -> str:
    m = int(total_minutes or 0)
    days = m // (60*24)
    hours = (m % (60*24)) // 60
    minutes = m % 60
    parts = []
    if days: parts.append(f"{days}j")
    if hours: parts.append(f"{hours}h")
    if minutes or not parts: parts.append(f"{minutes}m")
    return " ".join(parts)

# ================= INIT / CHECK =================
def check_files() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, "fonts"), exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, "audio", "openings"), exist_ok=True)

    for path in vars(FileConfig).values():
        if isinstance(path, str) and not os.path.exists(path):
            save_json(path, {})

def setup_bot() -> None:
    try:
        check_files()

        if not DISCORD_BOT_TOKEN:
            raise ValueError("Token Discord non configuré")

        # Vérif polices
        _ = load_font("Regular", 12)  # si fallback -> OK

        for pkg in ["requests", "pillow", "babel"]:
            try:
                __import__(pkg)
            except ImportError:
                logger.warning(f"Package {pkg} non installé")

        logger.info("Bot initialisé avec succès")
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation : {e}")
        raise
