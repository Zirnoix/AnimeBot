# restructured_bot/modules/history_data.py

import os
import json
from datetime import datetime

from . import core

HISTORY_FILE = os.path.join(core.DATA_DIR, "anime_history.json")


def load_history() -> list[dict]:
    """Charge l'historique des épisodes vus."""
    return core.load_json(HISTORY_FILE, [])


def save_history(history: list[dict]) -> None:
    """Enregistre l'historique des épisodes vus."""
    core.save_json(HISTORY_FILE, history)


def add_episode_to_history(entry: dict) -> None:
    """
    Ajoute un épisode à l'historique s'il n'existe pas déjà.

    Args:
        entry: Un dictionnaire avec les clés ``id``, ``title``, ``episode``, ``airingAt``.
    """
    history = load_history()
    uid = f"{entry['id']}-{entry['episode']}"
    if any(f"{e['id']}-{e['episode']}" == uid for e in history):
        return
    history.append({
        "id": entry["id"],
        "title": entry["title"],
        "episode": entry["episode"],
        "airingAt": entry["airingAt"],
        "logged_at": datetime.now(core.TIMEZONE).isoformat()
    })
    save_history(history)


def get_latest_history(limit: int = 10) -> list[dict]:
    """Retourne les derniers épisodes vus, triés du plus récent au plus ancien."""
    return sorted(load_history(), key=lambda e: e["logged_at"], reverse=True)[:limit]
