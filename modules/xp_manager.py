# modules/xp_manager.py

import json
import os

XP_FILE = "data/user_xp.json"

def load_xp():
    if not os.path.exists(XP_FILE):
        return {}
    with open(XP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_xp(xp_data):
    with open(XP_FILE, "w", encoding="utf-8") as f:
        json.dump(xp_data, f, ensure_ascii=False, indent=2)

def add_xp(user_id: str, amount: int):
    xp_data = load_xp()
    xp_data[user_id] = xp_data.get(user_id, 0) + amount
    save_xp(xp_data)

def get_xp(user_id: str):
    return load_xp().get(user_id, 0)

def get_rank_title(xp: int):
    if xp >= 1500:
        return "🌌 Légende"
    elif xp >= 1200:
        return "🐉 Maître"
    elif xp >= 900:
        return "🔥 Champion"
    elif xp >= 700:
        return "🎯 Expert"
    elif xp >= 500:
        return "🧠 Analyste"
    elif xp >= 350:
        return "📚 Connaisseur"
    elif xp >= 200:
        return "📖 Initié"
    elif xp >= 100:
        return "🌱 Amateur"
    elif xp >= 50:
        return "🐣 Apprenti"
    else:
        return "👶 Débutant"
