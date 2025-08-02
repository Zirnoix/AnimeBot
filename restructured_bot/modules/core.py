# core.py — Module central du bot AnimeBot

import os
import json
import unicodedata
import re
import io
import html
from datetime import datetime

import pytz
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import discord  # pour construire des Embed dans certaines fonctions

# === CONSTANTES GÉNÉRALES ===
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ANILIST_USERNAME = os.getenv("ANILIST_USERNAME")
OWNER_ID = int(os.getenv("DISCORD_OWNER_ID", "0"))
TIMEZONE = pytz.timezone("Europe/Paris")

# Chemins de fichiers de données
CONFIG_FILE = "data/config.json"
USER_SETTINGS_FILE = "data/user_settings.json"
TRACKER_FILE = "data/tracker.json"
NOTIFIED_FILE = "data/notified.json"
SCORES_FILE = "data/quiz_scores.json"
WINNER_FILE = "data/quiz_winner.json"
TITLE_CACHE_FILE = "data/anime_titles_cache.json"
PREFERENCES_FILE = "data/preferences.json"
LINKS_FILE = "data/links.json"
LEVELS_FILE = "data/levels.json"
MINI_SCORES_FILE = "data/mini_scores.json"

# Jours de la semaine en français
JOURS_FR = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
    "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"
}

# Répertoire des images emoji de genres (icônes personnalisées)
EMOJI_DIR = os.path.join(os.path.dirname(__file__), "Emojis")
EMOJI_MAP = {}
try:
    for filename in os.listdir(EMOJI_DIR):
        if filename.lower().endswith(".png"):
            genre = os.path.splitext(filename)[0]  # e.g. "Action.png" -> "Action"
            EMOJI_MAP[genre] = os.path.join(EMOJI_DIR, filename)
except Exception:
    pass

# === FONCTIONS UTILITAIRES ===

def normalize(text: str) -> str:
    """Normalise une chaîne de caractères (supprime accents et casse)."""
    if not text:
        return ""
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode().lower()

def clean_html(text: str) -> str:
    """Nettoie les balises HTML d’une chaîne de texte."""
    text = re.sub(r'<[^>]+>', '', text or '')
    return html.unescape(text)

# Gestion des émojis de genres (texte et images)
def genre_emoji(genres: list[str]) -> str:
    """Retourne un émoji texte représentatif du premier genre présent (ou 🎬 par défaut)."""
    mapping = {
        "Action": "⚔️", "Fantasy": "🧙", "Romance": "💖", "Comedy": "😂",
        "Drama": "🎭", "Horror": "👻", "Sci-Fi": "🚀", "Music": "🎵",
        "Sports": "⚽", "Slice of Life": "🍃", "Psychological": "🧠"
    }
    for g in genres:
        if g in mapping:
            return mapping[g]
    return "🎬"

def genre_emojis(genres: list[str]) -> list[str]:
    """Retourne la liste des chemins d’images emoji correspondant aux genres fournis."""
    return [path for g in genres if (path := EMOJI_MAP.get(g))]

# Chargement/sauvegarde générique de JSON
def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Erreur save_json: {path}] {e}")

# === FONCTIONS DE GESTION DES FICHIERS DE DONNÉES ===

def get_config():
    """Charge la configuration générale (ex: channel_id) depuis le fichier JSON."""
    return load_json(CONFIG_FILE, {})

def save_config(data):
    save_json(CONFIG_FILE, data)

def load_user_settings():
    """Charge les préférences utilisateur (rappels, résumé quotidien on/off, etc.)."""
    return load_json(USER_SETTINGS_FILE, {})

def save_user_settings(data):
    save_json(USER_SETTINGS_FILE, data)

def load_tracker():
    """Charge les données de suivi d'animes (listes personnalisées par utilisateur)."""
    return load_json(TRACKER_FILE, {})

def save_tracker(data):
    save_json(TRACKER_FILE, data)

def load_preferences():
    """Charge les préférences (heures d'alerte quotidienne) de chaque utilisateur."""
    return load_json(PREFERENCES_FILE, {})

def save_preferences(data):
    save_json(PREFERENCES_FILE, data)

def load_links():
    """Charge le mapping des comptes Discord vers pseudos AniList liés."""
    return load_json(LINKS_FILE, {})

def save_links(data):
    save_json(LINKS_FILE, data)

def load_scores():
    """Charge les scores de quiz de chaque utilisateur."""
    return load_json(SCORES_FILE, {})

def save_scores(data):
    save_json(SCORES_FILE, data)

def load_levels():
    """Charge les données de niveau/XP de chaque utilisateur."""
    return load_json(LEVELS_FILE, {})

def save_levels(data):
    save_json(LEVELS_FILE, data)

def load_mini_scores():
    """Charge les scores des mini-jeux (compteurs par type de jeu) de chaque utilisateur."""
    return load_json(MINI_SCORES_FILE, {})

def save_mini_scores(data):
    save_json(MINI_SCORES_FILE, data)

# === FONCTIONS LIÉES À ANILIST (API & PLANNING) ===

def query_anilist(query: str, variables: dict = None):
    """Envoie une requête GraphQL à l'API AniList et renvoie la réponse JSON."""
    try:
        resp = requests.post("https://graphql.anilist.co", json={"query": query, "variables": variables or {}})
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[Erreur AniList] Statut HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"[Erreur AniList] Exception pendant la requête : {e}")
        return None

def get_upcoming_episodes(username: str) -> list[dict]:
    """
    Récupère la liste des prochains épisodes à venir pour un utilisateur AniList donné (anime en cours ou en planning).
    """
    query = '''
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME, status_in: [CURRENT, PLANNING]) {
        lists {
          entries {
            media {
              id
              title { romaji }
              nextAiringEpisode {
                airingAt
                episode
              }
              coverImage { extraLarge }
              genres
            }
          }
        }
      }
    }
    '''
    try:
        data = query_anilist(query, {"name": username})
        if not data:
            return []
        upcoming = []
        for lst in data.get("data", {}).get("MediaListCollection", {}).get("lists", []):
            for entry in lst.get("entries", []):
                media = entry.get("media", {})
                next_ep = media.get("nextAiringEpisode")
                if not next_ep:
                    continue
                upcoming.append({
                    "id": media.get("id"),
                    "title": media.get("title", {}).get("romaji"),
                    "airingAt": next_ep.get("airingAt"),
                    "episode": next_ep.get("episode"),
                    "image": media.get("coverImage", {}).get("extraLarge"),
                    "genres": media.get("genres", [])
                })
        # Trier par date la plus proche
        return sorted(upcoming, key=lambda x: x["airingAt"])
    except Exception as e:
        print("[Erreur AniList] Échec de get_upcoming_episodes :", e)
        return []

def get_next_airing(user_id: int):
    """
    Renvoie les infos du prochain épisode à venir pour l’utilisateur Discord donné (si son compte AniList est lié).
    Retourne un dict avec 'media', 'airingAt' et 'episode'.
    """
    links = load_links()
    username = links.get(str(user_id))
    if not username:
        return None
    episodes = get_upcoming_episodes(username)
    if not episodes:
        return None
    # Épisode le plus proche
    next_ep = min(episodes, key=lambda e: e["airingAt"])
    # Préparer une structure similaire à l'AiringSchedule AniList
    media = {
        "title": {"romaji": next_ep["title"]},
        "coverImage": {"extraLarge": next_ep.get("image")},
        "genres": next_ep.get("genres", []),
        "episodes": None  # total d'épisodes non disponible ici
    }
    return {"media": media, "airingAt": next_ep["airingAt"], "episode": next_ep["episode"]}

def update_title_cache():
    """
    Met à jour le fichier de cache des titres (normalisés) des animés à venir pour le compte principal.
    """
    episodes = get_upcoming_episodes(ANILIST_USERNAME) or []
    titles = [normalize(ep["title"]) for ep in episodes]
    save_json(TITLE_CACHE_FILE, titles)

# === FONCTIONS LIÉES AUX COMPTES UTILISATEURS & PREFERENCES ===

def get_user_anilist(user_id: int) -> str | None:
    """Retourne le pseudo AniList lié à l’ID utilisateur Discord donné, ou None si non lié."""
    return load_links().get(str(user_id))

def add_to_tracker(user_id: int, title: str) -> bool:
    """Ajoute un titre d’anime à la liste de suivi personnalisée de l’utilisateur (pour rappels)."""
    tracker = load_tracker()
    uid = str(user_id)
    tracker.setdefault(uid, [])
    # Éviter les doublons (comparaison des titres normalisés)
    norm_title = normalize(title)
    for t in tracker[uid]:
        if normalize(t) == norm_title:
            return False
    tracker[uid].append(title)
    save_tracker(tracker)
    return True

def remove_from_tracker(user_id: int, title: str) -> bool:
    """Retire un titre d’anime de la liste de suivi personnalisée de l’utilisateur."""
    tracker = load_tracker()
    uid = str(user_id)
    if uid not in tracker:
        return False
    norm_title = normalize(title)
    for t in list(tracker[uid]):
        if normalize(t) == norm_title:
            tracker[uid].remove(t)
            if not tracker[uid]:
                tracker.pop(uid, None)
            save_tracker(tracker)
            return True
    return False

# === FONCTIONS DU SYSTÈME DE QUIZ & NIVEAUX ===

def add_xp(user_id: int, amount: int):
    """
    Ajoute de l'XP à l’utilisateur donné et gère la montée de niveau si seuil atteint.
    """
    levels = load_levels()
    uid = str(user_id)
    data = levels.get(uid, {"xp": 0, "level": 0})
    data["xp"] += amount
    # Monter de niveau tant que l’XP dépasse le seuil du prochain niveau
    while data["xp"] >= (data["level"] + 1) * 100:
        data["xp"] -= (data["level"] + 1) * 100
        data["level"] += 1
    levels[uid] = data
    save_levels(levels)

def add_mini_score(user_id: int, game: str, value: int = 1):
    """
    Incrémente le compteur de victoires/points pour un mini-jeu spécifique chez l’utilisateur.
    """
    scores = load_mini_scores()
    uid = str(user_id)
    scores.setdefault(uid, {})
    scores[uid][game] = scores[uid].get(game, 0) + value
    save_mini_scores(scores)

def get_mini_scores(user_id: int) -> dict:
    """Renvoie le dictionnaire des compteurs de mini-jeux pour l’utilisateur donné."""
    return load_mini_scores().get(str(user_id), {})

def get_xp_bar(xp: int, next_xp: int, length: int = 10) -> str:
    """
    Génère une barre de progression texte représentant l’XP courant par rapport à l’XP requis.
    """
    if next_xp <= 0:
        return "─" * length
    filled_count = int((xp / next_xp) * length)
    filled = "█" * filled_count
    empty = "─" * (length - filled_count)
    return filled + empty

def get_title_for_level(level: int) -> str:
    """
    Retourne un titre honorifique correspondant au niveau atteint par l’utilisateur.
    """
    if level >= 50:
        return "Légende de l'Anime"
    elif level >= 30:
        return "Maître Anime"
    elif level >= 20:
        return "Expert Anime"
    elif level >= 10:
        return "Otaku Confirmé"
    elif level >= 5:
        return "Fan d'Anime"
    else:
        return "Novice d'Anime"

# === FONCTIONS GRAPHIQUES (GÉNÉRATION D'IMAGES) ===

def load_font(size: int = 20, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Charge une police de caractères (essaie DejaVu puis Liberation, sinon défaut)."""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def generate_next_image(ep: dict, dt: datetime, tagline: str = "Prochain épisode") -> io.BytesIO | None:
    """
    Génère une image de notification pour un épisode à venir, à partir des données fournies.
    """
    width, height = 900, 500
    card = Image.new("RGB", (width, height), color=(30, 30, 30))
    # Charger et flouter l'image de fond (cover de l'anime)
    try:
        if ep.get("image"):
            response = requests.get(ep["image"], timeout=10)
            bg = Image.open(io.BytesIO(response.content)).convert("RGB").resize((width, height))
            bg = bg.filter(ImageFilter.GaussianBlur(radius=6))
            card.paste(bg)
    except Exception:
        pass
    draw = ImageDraw.Draw(card)
    title = ep.get("title", "Titre inconnu")
    episode_num = ep.get("episode", "?")
    genres = ep.get("genres", [])
    # Polices de texte
    title_font = load_font(40, bold=True)
    info_font = load_font(24)
    small_font = load_font(18)
    # Overlay sombre transparent
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 180))
    card.paste(overlay, (0, 0), overlay)
    # Texte principal (titre de l'anime)
    x, y = 50, 40
    draw.text((x, y), title, font=title_font, fill="white")
    y += title_font.getsize(title)[1] + 20
    jour_fr = JOURS_FR.get(dt.strftime("%A"), dt.strftime("%A"))
    date_str = dt.strftime("%d %b %Y • %H:%M")
    draw.text((x, y), f"{jour_fr} → {date_str}", font=info_font, fill=(220, 220, 220))
    y += info_font.getsize(date_str)[1] + 20
    draw.text((x, y), f"Épisode {episode_num}", font=info_font, fill="gold")
    # Tagline en bas de carte
    draw.text((x, height - 50), tagline, font=small_font, fill=(180, 180, 180))
    # Coller jusqu’à 5 émojis de genre en bas à droite
    emoji_size = 42
    emoji_paths = genre_emojis(genres)[:5]
    for i, emoji_path in enumerate(emoji_paths):
        try:
            emoji_img = Image.open(emoji_path).convert("RGBA").resize((emoji_size, emoji_size))
            card.paste(emoji_img, (width - (i+1)*(emoji_size+10), height - emoji_size - 20), emoji_img)
        except Exception:
            continue
    # Exporter l'image en mémoire
    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf

def generate_stats_card(user_name: str, avatar_url: str | None, anime_count: int, days_watched: float, mean_score: float, fav_genre: str) -> io.BytesIO:
    """
    Génère une image de carte de statistiques AniList personnalisée pour l’utilisateur.
    """
    width, height = 800, 400
    card = Image.new("RGB", (width, height), color=(20, 20, 20))
    draw = ImageDraw.Draw(card)
    # Charger l'avatar de l'utilisateur s'il est disponible
    avatar_img = None
    if avatar_url:
        try:
            resp = requests.get(avatar_url, timeout=10)
            avatar_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            avatar_img = avatar_img.resize((100, 100))
            # Appliquer un masque circulaire à l'avatar
            mask = Image.new("L", avatar_img.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, avatar_img.size[0], avatar_img.size[1]), fill=255)
            avatar_img.putalpha(mask)
        except Exception:
            avatar_img = None
    # Polices
    title_font = load_font(36, bold=True)
    label_font = load_font(24, bold=True)
    value_font = load_font(24)
    # Titre de la carte
    title_text = f"Statistiques AniList – {user_name}"
    draw.text((20, 20), title_text, font=title_font, fill="white")
    # Afficher l'avatar dans le coin (en haut à droite)
    if avatar_img:
        card.paste(avatar_img, (width - 120, 20), avatar_img)
    # Données statistiques (libellé : valeur)
    stats = [
        ("Animés vus", str(anime_count)),
        ("Temps total", f"{days_watched:.1f} jours"),
        ("Score moyen", str(round(mean_score, 1))),
        ("Genre favori", fav_genre),
    ]
    y = 80
    for label, value in stats:
        draw.text((20, y), f"{label} :", font=label_font, fill=(200, 200, 200))
        draw.text((250, y), value, font=value_font, fill="white")
        y += 40
    # Sauvegarder l'image dans un buffer mémoire
    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf

def generate_profile_card(user_name: str, avatar_url: str | None, level: int, xp: int, next_xp: int, quiz_score: int, mini_scores: dict) -> io.BytesIO:
    """
    Génère une image de carte de profil (niveau, XP, score quiz, mini-jeux) pour l’utilisateur.
    """
    width, height = 800, 500
    card = Image.new("RGB", (width, height), color=(25, 25, 40))
    draw = ImageDraw.Draw(card)
    # Charger l'avatar de l'utilisateur s'il est disponible
    avatar_img = None
    if avatar_url:
        try:
            resp = requests.get(avatar_url, timeout=10)
            avatar_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            avatar_size = 120
            avatar_img = avatar_img.resize((avatar_size, avatar_size))
            # Masque circulaire pour l'avatar
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
            avatar_img.putalpha(mask)
        except Exception:
            avatar_img = None
    # Polices
    name_font = load_font(32, bold=True)
    info_font = load_font(22)
    small_font = load_font(18)
    # Nom de l'utilisateur en en-tête
    draw.text((20, 20), user_name, font=name_font, fill=(255, 215, 0))
    # Avatar en haut à droite
    if avatar_img:
        card.paste(avatar_img, (width - 150, 20), avatar_img)
    # Niveau et XP
    level_text = f"Niveau {level}"
    xp_text = f"XP : {xp}/{next_xp}"
    bar = get_xp_bar(xp, next_xp, length=20)
    draw.text((20, 80), level_text, font=info_font, fill=(230, 230, 230))
    draw.text((20, 110), xp_text, font=info_font, fill=(230, 230, 230))
    draw.text((20, 140), f"[{bar}]", font=info_font, fill=(200, 200, 200))
    # Score de quiz
    draw.text((20, 180), f"Score Quiz : {quiz_score}", font=info_font, fill=(230, 230, 230))
    # Statistiques des mini-jeux
    draw.text((20, 220), "Mini-jeux :", font=info_font, fill=(230, 230, 230))
    y = 250
    name_map = {
        "animequiz": "Quiz",
        "higherlower": "Higher/Lower",
        "highermean": "Higher/Mean",
        "guessyear": "Guess Year",
        "guessepisodes": "Guess Ep.",
        "guessgenre": "Guess Genre",
        "duel": "Duel",
    }
    for game, val in mini_scores.items():
        label = name_map.get(game, game.capitalize())
        draw.text((40, y), f"- {label} : {val}", font=small_font, fill=(200, 200, 200))
        y += 25
    # Sauvegarde dans un buffer mémoire
    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf

# === FONCTIONS D’AIDE POUR EMBED DISCORD ===

MONTHS_FR = {
    "January": "janvier", "February": "février", "March": "mars", "April": "avril",
    "May": "mai", "June": "juin", "July": "juillet", "August": "août",
    "September": "septembre", "October": "octobre", "November": "novembre", "December": "décembre"
}

def format_date_fr(dt: datetime, pattern: str) -> str:
    """
    Formatte une date/heure selon un modèle donné en français.
    Exemples de pattern : "d MMMM" ou "EEEE d MMMM".
    """
    result = pattern
    # Jour de la semaine ("EEEE")
    if "EEEE" in pattern:
        result = result.replace("EEEE", JOURS_FR.get(dt.strftime("%A"), dt.strftime("%A")))
    # Mois de l'année ("MMMM")
    if "MMMM" in pattern:
        eng_month = dt.strftime("%B")
        result = result.replace("MMMM", MONTHS_FR.get(eng_month, eng_month))
    # Jour du mois ("d")
    if "d" in pattern:
        # On suppose que 'd' est un token isolé (non présent dans un mot)
        result = result.replace("d", str(dt.day))
    return result

def build_embed(ep: dict, dt: datetime) -> discord.Embed:
    """
    Construit un objet Embed Discord pour un rappel d'épisode imminent, à partir des infos d'un épisode.
    """
    title = f"📺 {ep['title']} — Épisode {ep['episode']} bientôt disponible"
    embed = discord.Embed(title=title, color=discord.Color.orange())
    # Ajouter une vignette avec la couverture de l'anime si disponible
    if ep.get("image"):
        embed.set_thumbnail(url=ep["image"])
    # Champ de date/heure de sortie
    jour = JOURS_FR.get(dt.strftime("%A"), dt.strftime("%A"))
    date_text = dt.strftime("%d/%m/%Y à %H:%M")
    embed.add_field(name="🗓️ Date de sortie", value=f"{jour} {date_text}", inline=False)
    return embed

# === FONCTION DE COMPARAISON DE STATS (DUEL ANILIST) ===

def get_duel_stats(user_id_1: int, user_id_2: int) -> discord.Embed | None:
    """
    Compare les statistiques AniList de deux utilisateurs (dont les comptes sont liés) et renvoie un Embed comparatif.
    """
    links = load_links()
    uid1, uid2 = str(user_id_1), str(user_id_2)
    if uid1 not in links or uid2 not in links:
        return None  # les deux utilisateurs doivent avoir lié leur compte AniList
    user1 = links[uid1]
    user2 = links[uid2]
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
    stats = {}
    for uname in (user1, user2):
        data = query_anilist(query, {"name": uname})
        try:
            anime_stats = data["data"]["User"]["statistics"]["anime"]
        except Exception:
            return None
        # Genre favori
        genres = anime_stats.get("genres", [])
        fav_genre = sorted(genres, key=lambda g: g["count"], reverse=True)
        fav_genre = fav_genre[0]["genre"] if fav_genre else "N/A"
        stats[uname] = {
            "count": anime_stats.get("count", 0) or 0,
            "score": round(anime_stats.get("meanScore") or 0, 1),
            "days": round((anime_stats.get("minutesWatched") or 0) / 1440, 1),
            "genre": fav_genre
        }
    s1, s2 = stats[user1], stats[user2]
    # Fonction interne de comparaison
    def compare(a, b):
        if a == b:
            return "🟰"  # égalité
        return "🔼" if a > b else "🔽"
    # Créer l'Embed résultat
    embed = discord.Embed(title=f"📊 Duel de stats : {user1} vs {user2}", color=discord.Color.blurple())
    embed.add_field(name="🎬 Animés vus", value=f"{s1['count']} vs {s2['count']} {compare(s1['count'], s2['count'])}", inline=False)
    embed.add_field(name="⭐ Score moyen", value=f"{s1['score']} vs {s2['score']} {compare(s1['score'], s2['score'])}", inline=False)
    embed.add_field(name="🕒 Jours regardés", value=f"{s1['days']} vs {s2['days']} {compare(s1['days'], s2['days'])}", inline=False)
    embed.add_field(name="🎭 Genre favori", value=f"{s1['genre']} vs {s2['genre']}", inline=False)
    return embed
