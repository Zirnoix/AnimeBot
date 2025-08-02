import os
import json
import unicodedata
import re
from datetime import datetime
import pytz
import requests

from .genre_emoji import genre_emojis

# === CONFIGURATION ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ANILIST_USERNAME = os.getenv("ANILIST_USERNAME")
TIMEZONE = pytz.timezone("Europe/Paris")

CONFIG_FILE = "data/config.json"
USER_SETTINGS_FILE = "data/user_settings.json"
TRACKER_FILE = "data/tracker.json"
NOTIFIED_FILE = "data/notified.json"
SCORES_FILE = "data/quiz_scores.json"
WINNER_FILE = "data/quiz_winner.json"
TITLE_CACHE_FILE = "data/anime_titles_cache.json"
PREFERENCES_FILE = "data/preferences.json"

JOURS_FR = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
    "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"
}


# === UTILS ===

def normalize(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode().lower()


def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Erreur save_json: {path}] {e}")


# === FICHIERS ===

def get_config():
    return load_json(CONFIG_FILE, {})


def get_upcoming_episodes(username: str) -> list[dict]:
    query = '''
    query ($name: String) {
      MediaListCollection(userName: $name, type: ANIME, status_in: [CURRENT, PLANNING]) {
        lists {
          entries {
            media {
              id
              title {
                romaji
              }
              nextAiringEpisode {
                airingAt
                episode
              }
              coverImage {
                extraLarge
              }
              genres
            }
          }
        }
      }
    }
    '''
    try:
        response = requests.post("https://graphql.anilist.co", json={"query": query, "variables": {"name": username}})
        data = response.json()
        upcoming = []
        for lst in data["data"]["MediaListCollection"]["lists"]:
            for entry in lst["entries"]:
                media = entry["media"]
                next_ep = media.get("nextAiringEpisode")
                if not next_ep:
                    continue
                upcoming.append({
                    "id": media["id"],
                    "title": media["title"]["romaji"],
                    "airingAt": next_ep["airingAt"],
                    "episode": next_ep["episode"],
                    "image": media["coverImage"]["extraLarge"],
                    "genres": media.get("genres", []),
                })
        return sorted(upcoming, key=lambda x: x["airingAt"])
    except Exception as e:
        print("[Erreur AniList]", e)
        return []


def load_user_settings():
    return load_json(USER_SETTINGS_FILE, {})


def load_tracker():
    return load_json(TRACKER_FILE, {})


def load_scores():
    return load_json(SCORES_FILE, {})


def save_scores(data):
    save_json(SCORES_FILE, data)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_title_cache():
    episodes = get_upcoming_episodes(ANILIST_USERNAME)
    titles = [normalize(ep["title"]) for ep in episodes]
    with open(TITLE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False, indent=2)


def load_preferences():
    return load_json(PREFERENCES_FILE, {})
