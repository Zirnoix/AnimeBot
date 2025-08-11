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
import re
import unicodedata
import random
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional, Dict, List, Set, Union, Tuple, Iterable
import discord
import requests
import pytz
from zoneinfo import ZoneInfo
import aiohttp
import aiofiles
from babel.dates import format_datetime
from PIL import Image, ImageDraw, ImageFont
import io

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

###############################################################################
# Configuration et chemins
###############################################################################
    
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets')
WINNER_FILE = os.path.join(DATA_DIR, "winner.json")
TITLES_FILE = "data/user_titles.json"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)
logger = logging.getLogger(__name__)
CACHE_FILE = "data/anime_titles.json"

class FileConfig:
    """Configuration des chemins de fichiers."""

    PREFERENCES = os.path.join(DATA_DIR, "preferences.json")
    QUIZ_SCORES = os.path.join(DATA_DIR, "quiz_scores.json")
    LINKED_USERS = os.path.join(DATA_DIR, "linked_users.json")
    LEVELS = os.path.join(DATA_DIR, "quiz_levels.json")
    TRACKER = os.path.join(DATA_DIR, "anitracker.json")
    USER_SETTINGS = os.path.join(DATA_DIR, "user_settings.json")
    NOTIFIED = os.path.join(DATA_DIR, "notified.json")
    LINKS = os.path.join(DATA_DIR, "user_links.json")
    TITLE_CACHE = os.path.join(DATA_DIR, "title_cache.json")
    WINNER = os.path.join(DATA_DIR, "quiz_winner.json")
    MINI_SCORES = os.path.join(DATA_DIR, "mini_scores.json")
    CONFIG = os.path.join(DATA_DIR, "config.json")
    GUESSOP_SCORES = os.path.join(DATA_DIR, "guessop_scores.json")
    GUESSCHAR_SCORES = os.path.join(DATA_DIR, "guesschar_scores.json")

# Variables d'environnement et constantes
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ANILIST_USERNAME = os.getenv("ANILIST_USERNAME", "Zirnoixdcoco")
TIMEZONE = pytz.timezone(os.getenv("BOT_TIMEZONE", "Europe/Paris"))
OWNER_ID = 180389173985804288

# Constantes pour les dates
JOURS_FR = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
    "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi",
    "Sunday": "Dimanche"
}

# Émojis pour les genres
GENRE_EMOJIS = {
    "Action": "⚔️", "Comedy": "😂", "Drama": "🎭", "Fantasy": "🧙‍♂️",
    "Romance": "💕", "Sci-Fi": "🚀", "Horror": "👻", "Mystery": "🕵️",
    "Sports": "🏅", "Music": "🎵", "Slice of Life": "🍃",
    "Adventure": "🌍", "Supernatural": "🔮", "Mecha": "🤖",
    "Psychological": "🧠", "Thriller": "🔪"
}

# Titres de niveaux (paliers de 5 niveaux)
LEVEL_TITLES_QUIZ = [
    (0, "👶 Nouveau"),
    (5, "🌱 Apprenti"),
    (10, "📘 Amateur"),
    (15, "📚 Otaku Confirmé"),
    (20, "🎯 Expert"),
    (25, "🔥 Maître Otaku"),
    (30, "🧠 Sensei"),
    (35, "🧩 Stratège"),
    (40, "🏆 Champion"),
    (45, "🌟 Légende Locale"),
    (50, "💎 Légende Nationale"),
    (55, "🗿 Icône Anime"),
    (60, "🐉 Mythe"),
    (65, "🛐 Dieu Otaku"),
    (70, "☄️ Divinité Universelle"),
    (75, "🔮 Omniscient Otaku"),
    (80, "⚡ Maître des Éclairs"),
    (85, "🌌 Voyageur Galactique"),
    (90, "🏮 Gardien des Animes"),
    (95, "🎭 Maître des Illusions"),
    (100, "👑 Roi des Otakus")
]

# --- Titres pour le niveau GLOBAL (XP) ---
# paliers : +3 jusqu'à 15, +5 jusqu'à 30, puis +7 jusqu'à 150
LEVEL_TITLES_GLOBAL = [
    (0,   "👶 Novice"),
    (3,   "🌱 Initié"),
    (6,   "📗 Débutant"),
    (9,   "🔧 Pratiquant"),
    (12,  "🧭 Explorateur"),
    (15,  "🎯 Approuvé"),
    (20,  "⚔️ Aspirant"),
    (25,  "🏹 Disciple"),
    (30,  "🛡️ Chevalier"),
    (37,  "🧠 Stratège"),
    (44,  "🔥 Maître"),
    (51,  "🌪️ Virtuose"),
    (58,  "💎 Élite"),
    (65,  "🌟 Héroïque"),
    (72,  "🐉 Archon"),
    (79,  "⚡ Dominant"),
    (86,  "🌌 Mythique"),
    (93,  "🏆 Parangon"),
    (100, "👑 Souverain"),
    (107, "🗼 Éminence"),
    (114, "🜲 Arcaniste"),
    (121, "🪽 Séraphin"),
    (128, "☄️ Sidéral"),
    (135, "🜚 Transcendant"),
    (142, "🛐 Divin"),
    (150, "♾️ Apothéose"),
]

###############################################################################
# Fonctions de gestion JSON et données de base
###############################################################################

def load_titles():
    if os.path.exists(TITLES_FILE):
        with open(TITLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_titles(titles):
    with open(TITLES_FILE, "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False, indent=2)
        
def load_json(path: str, default: Any) -> Any:
    """Charge des données depuis un fichier JSON.

    Args:
        path: Chemin du fichier
        default: Valeur par défaut si le fichier n'existe pas

    Returns:
        Les données chargées ou la valeur par défaut
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur lors du chargement de {path}: {e}")
        return default


def save_json(path: str, data: Any) -> None:
    """Sauvegarde des données dans un fichier JSON.

    Args:
        path: Chemin du fichier
        data: Données à sauvegarder
    """
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de {path}: {e}")


###############################################################################
# Gestion des scores, niveaux et mini-jeux
###############################################################################

def xp_for_next_level(level: int) -> int:
    base_xp = 50
    growth = 1.08
    return int(base_xp * (growth ** level))

def load_scores() -> dict:
    """Charge les scores du quiz."""
    return load_json(FileConfig.QUIZ_SCORES, {})


def save_scores(scores: dict) -> None:
    """Sauvegarde les scores du quiz."""
    save_json(FileConfig.QUIZ_SCORES, scores)


def load_levels() -> dict:
    """Charge les niveaux des utilisateurs."""
    return load_json(FileConfig.LEVELS, {})


def save_levels(data: dict) -> None:
    """Sauvegarde les niveaux des utilisateurs."""
    save_json(FileConfig.LEVELS, data)


# core.py
async def add_xp(bot, channel, user_id: int, amount: int, announce: bool = True):
    levels = load_levels()
    key = str(user_id)
    data = levels.get(key, {"xp": 0, "level": 0})

    old_level = int(data.get("level", 0))
    old_title = get_title_for_global_level(old_level)  # <-- rang AVANT

    # Ajout d’XP
    data["xp"] = int(data.get("xp", 0)) + int(amount)

    # Level-up avec la même courbe que partout (xp_for_next_level)
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

    # Nouveau rang APRES
    new_level = int(data["level"])
    new_title = get_title_for_global_level(new_level)

    # 👉 Annoncer UNIQUEMENT si rang (titre) a changé
    if announce and (new_title != old_title):
        try:
            await channel.send(
                f"🎉 **<@{user_id}>** atteint le rang **{new_title}** (niv. {new_level}) !"
            )
        except Exception:
            pass

    return {"leveled": leveled, "old_level": old_level, "new_level": new_level,
            "old_title": old_title, "new_title": new_title}

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


def format_airing_datetime_fr(ts: int, tz_name: str = "Europe/Paris") -> str:
    if not ts:
        return "date inconnue"
    dt_local = datetime.fromtimestamp(ts, tz=ZoneInfo(tz_name))
    months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    weekdays = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    wd = weekdays[dt_local.weekday()]
    mo = months[dt_local.month - 1]
    return f"{wd} {dt_local.day} {mo} {dt_local:%H:%M}"


def get_next_airing_one() -> Optional[Dict[str, Any]]:
    """
    Récupère le tout prochain épisode à sortir (global).
    Champs : title_*, episode, airingAt, cover, genres
    """
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
    """Retourne les infos du prochain épisode pour un titre donné."""
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
        result = query_anilist(query, {"search": title})
        if not result or "data" not in result or not result["data"]["Media"]:
            return None
        media = result["data"]["Media"]
        if not media.get("nextAiringEpisode"):
            return None
        return {
            "title_romaji": media["title"]["romaji"],
            "title_english": media["title"]["english"],
            "title_native": media["title"]["native"],
            "episode": media["nextAiringEpisode"]["episode"],
            "airingAt": media["nextAiringEpisode"]["airingAt"],
            "cover": media["coverImage"]["extraLarge"] or media["coverImage"]["large"],
            "format": media["format"],
            "season": media["season"],
            "seasonYear": media["seasonYear"]
        }
    except Exception as e:
        LOG.error(f"Erreur get_next_airing_for_title({title}): {e}")
        return None


def load_mini_scores() -> dict:
    """Charge les scores des mini-jeux."""
    return load_json(FileConfig.MINI_SCORES, {})


def save_mini_scores(data: dict) -> None:
    """Sauvegarde les scores des mini-jeux."""
    save_json(FileConfig.MINI_SCORES, data)


def add_mini_score(user_id: int, game: str, amount: int = 1) -> None:
    """Ajoute un score à un mini-jeu.

    Args:
        user_id: ID Discord de l'utilisateur
        game: Nom du mini-jeu
        amount: Points à ajouter
    """
    data = load_mini_scores()
    uid = str(user_id)
    data.setdefault(uid, {})
    data[uid][game] = data[uid].get(game, 0) + amount
    save_mini_scores(data)


def get_mini_scores(user_id: int) -> dict:
    """Récupère tous les scores mini-jeux d'un utilisateur."""
    data = load_mini_scores()
    return data.get(str(user_id), {})


###############################################################################
# Gestion des liens et préférences utilisateurs
###############################################################################

def load_links() -> dict:
    """Charge les liens entre comptes Discord et AniList."""
    return load_json(FileConfig.LINKED_USERS, {})


def save_links(data: dict) -> None:
    """Sauvegarde les liens entre comptes."""
    save_json(FileConfig.LINKED_USERS, data)


def get_user_anilist(user_id: int) -> Optional[str]:
    """Récupère le pseudo AniList lié à un ID Discord."""
    links = load_links()
    return links.get(str(user_id))

def get_user_stats(user_id: int):
    """Alias pour compatibilité avec l’ancienne commande mystats."""
    return get_game_stats(user_id)

def load_preferences() -> dict:
    """Charge les préférences utilisateurs."""
    return load_json(FileConfig.PREFERENCES, {})


def save_preferences(data: dict) -> None:
    """Sauvegarde les préférences utilisateurs."""
    save_json(FileConfig.PREFERENCES, data)


def load_user_settings() -> dict:
    """Charge les paramètres utilisateurs."""
    return load_json(FileConfig.USER_SETTINGS, {})


def save_user_settings(settings: dict) -> None:
    """Sauvegarde les paramètres utilisateurs."""
    save_json(FileConfig.USER_SETTINGS, settings)


def load_tracker() -> dict:
    """Charge le tracker d'animes."""
    return load_json(FileConfig.TRACKER, {})


def save_tracker(data: dict) -> None:
    """Sauvegarde le tracker d'animes."""
    save_json(FileConfig.TRACKER, data)


###############################################################################
# API AniList et requêtes
###############################################################################


import time  # en haut du fichier


import requests

def query_anilist(query: str, variables: dict = None) -> dict:
    url = "https://graphql.anilist.co"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {"query": query, "variables": variables or {}}

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            return {}
    except Exception as e:
        print(f"[AniList] Erreur : {e}")
        return {}

def load_cached_titles() -> list[dict]:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
    
def get_upcoming_episodes(username: str) -> list[dict]:
    """Récupère les prochains épisodes pour un utilisateur.

    Args:
        username: Nom d'utilisateur AniList

    Returns:
        Liste des épisodes à venir avec leurs informations
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
    try:
        data = query_anilist(query, {"name": username})
        if not data or "data" not in data:
            return []

        episodes = []
        for lst in data["data"]["MediaListCollection"]["lists"]:
            for entry in lst["entries"]:
                media = entry.get("media", {})
                next_ep = media.get("nextAiringEpisode")
                if not next_ep:
                    continue

                episodes.append({
                    "mediaId": media.get("id"),
                    "title": media["title"]["romaji"],
                    "episode": next_ep["episode"],
                    "airingAt": next_ep["airingAt"],
                    "genres": media.get("genres", []),
                    "image": media.get("coverImage", {}).get("extraLarge")
                })
        return episodes
    except Exception as e:
        logger.error(f"Erreur récupération épisodes: {e}")
        return []


def get_anime_details(media_id: int) -> Optional[dict]:
    """Récupère les détails d'un anime spécifique.

    Args:
        media_id: ID de l'anime sur AniList

    Returns:
        Détails de l'anime ou None en cas d'erreur
    """
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
    """Récupère les détails d'un personnage (avec cache).

    Args:
        char_id: ID du personnage sur AniList

    Returns:
        Détails du personnage ou None en cas d'erreur
    """
    query = '''
    query ($id: Int) {
      Character(id: $id) {
        name { full native }
        image { large }
        description
        gender
        dateOfBirth { month day }
        age
        media {
          nodes {
            title { romaji }
            type
          }
        }
      }
    }
    '''
    try:
        data = query_anilist(query, {"id": char_id})
        return data["data"]["Character"] if data and "data" in data else None
    except Exception as e:
        logger.error(f"Erreur récupération personnage: {e}")
        return None


###############################################################################
# Gestion des titres et du cache
###############################################################################

def normalize_title(title: str) -> str:
    """Normalise un titre pour la recherche.

    Args:
        title: Titre à normaliser

    Returns:
        Titre normalisé
    """
    # Nettoyage basique
    title = normalize(title)

    # Supprimer les mots communs
    stop_words = {"the", "a", "an", "season", "part", "episode", "movie", "saison"}
    words = [w for w in title.split() if w not in stop_words]

    # Supprimer les marqueurs de saison/partie
    clean = re.sub(
        r"(s\d|season \d|part \d|[^\w\s])",
        "",
        " ".join(words),
        flags=re.IGNORECASE
    )

    return clean.strip()


def find_similar_titles(query: str, threshold: float = 0.85) -> list[str]:
    """Trouve des titres similaires dans le cache.

    Args:
        query: Titre recherché
        threshold: Seuil de similarité (0-1)

    Returns:
        Liste des titres similaires trouvés
    """
    query = normalize_title(query)
    cache = load_json(FileConfig.TITLE_CACHE, [])
    matches = []

    for title in cache:
        if not title:
            continue

        # Vérification exacte
        if query == title:
            matches.append(title)
            continue

        # Vérification partielle
        if query in title or title in query:
            matches.append(title)
            continue

        # Vérification de similarité
        if difflib.SequenceMatcher(None, query, title).ratio() >= threshold:
            matches.append(title)

    return matches


###############################################################################
# Génération d'images
###############################################################################

def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Charge une police avec gestion des erreurs.

    Args:
        name: Nom de la police ("Bold" ou "Regular")
        size: Taille de la police

    Returns:
        Police chargée ou police par défaut en cas d'erreur
    """
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
    """Génère une carte de statistiques personnalisée.

    Args:
        user_name: Nom de l'utilisateur
        avatar_url: URL de l'avatar Discord
        anime_count: Nombre d'animés vus
        days_watched: Jours de visionnage
        mean_score: Score moyen
        fav_genre: Genre favori

    Returns:
        Buffer contenant l'image générée
    """
    # Dimensions de base
    width, height = 900, 500
    card = Image.new("RGB", (width, height), color=(25, 25, 35))
    draw = ImageDraw.Draw(card)

    # Chargement des polices
    font_title = load_font("Bold", 40)
    font_stats = load_font("Regular", 30)

    # Avatar
    if avatar_url:
        try:
            response = requests.get(avatar_url, timeout=10)
            avatar = Image.open(io.BytesIO(response.content)).convert("RGBA")

            # Création du masque circulaire
            size = 150
            mask = Image.new("L", (size, size), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, size, size), fill=255)

            # Redimensionnement et application du masque
            avatar = avatar.resize((size, size))
            card.paste(avatar, (50, 50), mask)
        except Exception as e:
            logger.error(f"Erreur chargement avatar: {e}")

    # Titre et statistiques
    title_x = 250
    stats_y = 150

    draw.text((title_x, 50), f"Statistiques de {user_name}",
              font=font_title, fill=(255, 255, 255))

    stats = [
        (f"🎬 Animés vus : {anime_count}", (255, 200, 100)),
        (f"🕒 Temps total : {days_watched:.1f} jours", (100, 200, 255)),
        (f"⭐ Score moyen : {mean_score:.1f}", (255, 100, 100)),
        (f"🎭 Genre favori : {fav_genre}", (200, 255, 100))
    ]

    for i, (text, color) in enumerate(stats):
        draw.text((title_x, stats_y + i * 60), text,
                  font=font_stats, fill=color)

    # Sauvegarde
    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf


def generate_next_image(ep: dict, dt: datetime, tagline: str = "Prochain épisode") -> io.BytesIO:
    """Génère une image pour le prochain épisode.

    Args:
        ep: Informations sur l'épisode
        dt: Date et heure de diffusion
        tagline: Texte descriptif

    Returns:
        Buffer contenant l'image générée
    """
    width, height = 900, 500
    card = Image.new("RGB", (width, height), color=(20, 20, 20))
    draw = ImageDraw.Draw(card)

    # Chargement des polices
    font_title = load_font("Bold", 34)
    font_sub = load_font("Regular", 24)
    font_small = load_font("Regular", 20)

    # Image de couverture
    try:
        if ep.get("image"):
            response = requests.get(ep["image"], timeout=10)
            cover = Image.open(io.BytesIO(response.content)).convert("RGBA")

            # Redimensionnement avec ratio
            cover_width = int(width * 0.45)
            ratio = cover.width / cover.height

            if ratio > cover_width / height:
                new_width = int(height * ratio)
                cover = cover.resize((new_width, height))
                left = (new_width - cover_width) // 2
                cover = cover.crop((left, 0, left + cover_width, height))
            else:
                new_height = int(cover_width / ratio)
                cover = cover.resize((cover_width, new_height))
                top = (new_height - height) // 2
                cover = cover.crop((0, top, cover_width, top + height))

            card.paste(cover, (0, 0))
    except Exception as e:
        logger.error(f"Erreur chargement cover: {e}")

    # Overlay sombre
    overlay = Image.new("RGBA", (width - cover_width, height), (0, 0, 0, 180))
    card.paste(overlay, (cover_width, 0), overlay)

    # Textes
    x0 = cover_width + 30
    y = 30

    # Titre avec retour à la ligne
    title = ep.get("title", "Titre inconnu")
    max_width = width - cover_width - 60
    words = title.split()
    line = ""

    for word in words:
        test_line = f"{line} {word}".strip()
        w, h = draw.textsize(test_line, font=font_title)
        if w <= max_width:
            line = test_line
        else:
            draw.text((x0, y), line, font=font_title, fill=(255, 255, 255))
            y += h + 10
            line = word

    if line:
        draw.text((x0, y), line, font=font_title, fill=(255, 255, 255))

    # Informations épisode
    y += 60
    draw.text((x0, y), f"Épisode {ep['episode']}",
              font=font_sub, fill=(255, 215, 0))

    y += 40
    date_str = format_date_fr(dt, "EEEE d MMMM à HH:mm")
    draw.text((x0, y), date_str, font=font_sub, fill=(200, 200, 200))

    # Tagline
    draw.text((x0, height - 50), tagline,
              font=font_small, fill=(150, 150, 150))

    # Sauvegarde
    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf

def generate_profile_card(user_name, avatar_url, level, xp, next_xp, quiz_score, mini_scores):
    # Image de fond
    width, height = 800, 400
    bg = Image.new("RGBA", (width, height), (25, 25, 30))
    draw = ImageDraw.Draw(bg)

    # Avatar Discord (arrondi)
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

    # Polices (à adapter si besoin)
    try:
        font_title = ImageFont.truetype("arialbd.ttf", 32)
        font_text = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)

    # Infos principales
    draw.text((220, 40), f"{user_name}", font=font_title, fill=(255, 255, 255))
    draw.text((220, 90), f"Niveau {level} – {xp}/{next_xp} XP", font=font_text, fill=(200, 200, 200))
    draw.text((220, 120), f"🏆 Score Quiz : {quiz_score}", font=font_text, fill=(230, 230, 230))
    draw.text((220, 160), "🎮 Mini‑jeux :", font=font_text, fill=(255, 255, 255))

    # Statistiques mini-jeux
    y = 190
    mapping = {
        "animequiz": "Quiz",
        "higherlower": "Higher/Lower",
        "highermean": "Higher/Mean",
        "guessyear": "Guess Year",
        "guessepisodes": "Guess Episodes",
        "guessgenre": "Guess Genre",
        "duel": "Duel",
    }
    for key, val in mini_scores.items():
        name = mapping.get(key, key.replace("_", " ").capitalize())
        draw.text((240, y), f"- {name} : {val}", font=font_text, fill=(180, 180, 180))
        y += 28

    # Enregistrement en mémoire
    buffer = BytesIO()
    bg.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer

###############################################################################
# Fonctions utilitaires et formatage
###############################################################################

def normalize(text: str | None) -> str:
    """Normalise un texte (supprime accents, met en minuscules, etc.).

    Args:
        text: Texte à normaliser

    Returns:
        Texte normalisé
    """
    if not text:
        return ""
    # Supprime les accents
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    # Garde uniquement les caractères alphanumériques et espaces
    return ''.join(e for e in text.lower()
                   if e.isalnum() or e.isspace()).strip()


def format_date_fr(dt: datetime, pattern: str = "EEEE d MMMM") -> str:
    """Formate une date en français.

    Args:
        dt: Date à formater
        pattern: Format souhaité

    Returns:
        Date formatée en français
    """
    return format_datetime(dt, pattern, locale='fr_FR').capitalize()


def genre_emoji(genres: list[str]) -> str:
    """Retourne un emoji correspondant au genre principal.

    Args:
        genres: Liste des genres

    Returns:
        Emoji correspondant au premier genre reconnu
    """
    if not genres:
        return "🎬"

    for genre in genres:
        if emoji := GENRE_EMOJIS.get(genre):
            return emoji
    return "🎬"


def get_xp_bar(xp: int, next_xp: int, length: int = 20) -> str:
    """Génère une barre de progression textuelle.

    Args:
        xp: XP actuel
        next_xp: XP nécessaire pour le niveau suivant
        length: Longueur de la barre

    Returns:
        Barre de progression avec caractères pleins/vides
    """
    filled = int((xp / next_xp) * length)
    return "▰" * filled + "▱" * (length - filled)


###############################################################################
# Configuration du bot et notifications
###############################################################################

def get_config() -> dict:
    """Charge la configuration globale du bot."""
    config = load_json(FileConfig.CONFIG, {})
    if not config:
        config.update({
            "channel_id": None,
            "notification_delay": 10,  # Minutes
            "daily_summary": True,
            "default_alert_time": "08:00"
        })
        save_config(config)
    return config


def save_config(config: dict) -> None:
    """Sauvegarde la configuration globale du bot."""
    save_json(FileConfig.CONFIG, config)


def should_notify(ep: dict) -> bool:
    """Vérifie si un épisode doit être notifié.

    Args:
        ep: Informations sur l'épisode

    Returns:
        True si l'épisode doit être notifié
    """
    if not ep.get("airingAt"):
        return False

    now = datetime.now(timezone.utc).timestamp()
    config = get_config()
    delay = config.get("notification_delay", 10) * 60  # En secondes

    return abs(ep["airingAt"] - now) <= delay

def get_my_next_airing_one() -> Optional[Dict[str, Any]]:
    """
    Prochain épisode à sortir pour l'utilisateur défini par ANILIST_USERNAME.
    Parcourt toute la liste CURRENT (pagination) et prend le plus proche dans le futur.
    """
    username = os.getenv("ANILIST_USERNAME")
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

        if not page_data.get("pageInfo", {}).get("hasNextPage"):
            break
        page += 1

    return best

def get_linked_anilist(discord_id: int):
    """Retourne le pseudo AniList lié à un utilisateur Discord."""
    links = load_links()
    return links.get(str(discord_id))

def get_anilist_stats(username: str) -> Optional[Dict[str, Any]]:
    """
    Récupère les stats AniList d'un utilisateur.
    Retourne: {count, minutesWatched, meanScore, favoriteGenre}
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
        # genre le plus fréquent
        fav_genre = max(genres, key=lambda g: g.get("count", 0)).get("genre")

    return {
        "count": anim.get("count", 0),
        "minutesWatched": anim.get("minutesWatched", 0),
        "meanScore": anim.get("meanScore", 0),
        "favoriteGenre": fav_genre or "—",
    }

def get_anilist_stats_for_discord(discord_id: int, fallback_env: bool = True) -> Optional[Dict[str, Any]]:
    """
    Stats pour un utilisateur Discord:
    - si lié: son AniList
    - sinon (optionnel): fallback sur ANILIST_USERNAME si défini
    """
    username = get_linked_anilist(discord_id)
    if not username and fallback_env:
        username = os.getenv("ANILIST_USERNAME")
    if not username:
        return None
    return get_anilist_stats(username)

def humanize_minutes(total_minutes: int) -> str:
    """Convertit des minutes en 'Xd Yh Zm' propre."""
    m = int(total_minutes or 0)
    days = m // (60*24)
    hours = (m % (60*24)) // 60
    minutes = m % 60
    parts = []
    if days: parts.append(f"{days}j")
    if hours: parts.append(f"{hours}h")
    if minutes or not parts: parts.append(f"{minutes}m")
    return " ".join(parts)
    
def get_user_next_airing_one(username: str):
    """
    Retourne le prochain épisode à venir pour un utilisateur AniList.
    """
    query = """
    query ($userName: String) {
      MediaListCollection(userName: $userName, type: ANIME, status_in: [CURRENT]) {
        lists {
          entries {
            media {
              title {
                romaji
                english
                native
              }
              coverImage {
                large
              }
              genres
              nextAiringEpisode {
                episode
                airingAt
              }
            }
          }
        }
      }
    }
    """
    data = query_anilist(query, {"userName": username})

    entries = []
    for lst in data.get("MediaListCollection", {}).get("lists", []):
        for entry in lst.get("entries", []):
            media = entry.get("media")
            if media.get("nextAiringEpisode"):
                entries.append(media)

    if not entries:
        return None

    entries.sort(key=lambda m: m["nextAiringEpisode"]["airingAt"])
    m = entries[0]
    return {
        "title_romaji": m["title"].get("romaji"),
        "title_english": m["title"].get("english"),
        "title_native": m["title"].get("native"),
        "cover": m["coverImage"]["large"],
        "episode": m["nextAiringEpisode"]["episode"],
        "airingAt": m["nextAiringEpisode"]["airingAt"],
        "genres": m.get("genres", [])
    }

###############################################################################
# Mini-jeux et quiz
###############################################################################

def get_game_stats(user_id: int) -> dict:
    """Récupère les statistiques complètes d'un utilisateur.

    Args:
        user_id: ID Discord de l'utilisateur

    Returns:
        Dictionnaire avec toutes les stats
    """
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
    """Formate le nom d'un mini-jeu pour l'affichage.

    Args:
        game: Identifiant du mini-jeu

    Returns:
        Nom formaté du mini-jeu
    """
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


###############################################################################
# Initialisation et vérification
###############################################################################

def check_files() -> None:
    """Vérifie et crée les fichiers nécessaires."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, "fonts"), exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, "audio", "openings"), exist_ok=True)

    for path in vars(FileConfig).values():
        if isinstance(path, str) and not os.path.exists(path):
            save_json(path, {})


def setup_bot() -> None:
    """Configure le bot et vérifie les dépendances."""
    try:
        check_files()

        if not DISCORD_BOT_TOKEN:
            raise ValueError("Token Discord non configuré")

        # Vérification des polices
        test_font = load_font("Regular", 12)
        if isinstance(test_font, ImageFont.load_default().__class__):
            logger.warning("Police par défaut utilisée - les polices personnalisées ne sont pas disponibles")

        # Vérification des dépendances
        for pkg in ["requests", "pillow", "babel"]:
            try:
                __import__(pkg)
            except ImportError:
                logger.warning(f"Package {pkg} non installé")

        logger.info("Bot initialisé avec succès")

    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation : {e}")
        raise
