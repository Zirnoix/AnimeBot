# modules/history_data.py

import json
import os
from datetime import datetime

HISTORY_FILE = "data/history.json"


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def add_to_history(category: str, entry_id: str):
    history = load_history()
    if category not in history:
        history[category] = []
    if entry_id not in history[category]:
        history[category].append(entry_id)
    save_history(history)


def was_already_posted(category: str, entry_id: str) -> bool:
    history = load_history()
    return entry_id in history.get(category, [])

def get_today_anime_data():
    """Retourne les épisodes prévus pour aujourd’hui à partir du fichier history.json"""
    if not os.path.exists(HISTORY_FILE):
        return []

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    return data.get(today, [])
