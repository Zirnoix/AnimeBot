import json
import os
import pytz
from datetime import datetime

TIMEZONE = pytz.timezone("Europe/Paris")
jours_fr = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
    "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"
}

def load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def genre_emoji(genres):
    known = {
        "Action": "⚔️", "Comedy": "😂", "Drama": "🎭", "Fantasy": "🧚",
        "Horror": "👻", "Romance": "❤️", "Sci-Fi": "🚀", "Slice of Life": "🍰",
        "Sports": "🏅", "Supernatural": "✨", "Mystery": "🕵️", "Adventure": "🌍"
    }
    return "".join(known.get(g, "") for g in genres if g in known) or "🎬"