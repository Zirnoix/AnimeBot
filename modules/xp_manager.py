import json
import os
import datetime

XP_FILE = "xp_data.json"
WINNERS_FILE = "monthly_winners.json"
TITLES = [
    (100, "🌌 Légende"),
    (80, "🔥 Champion"),
    (60, "🎯 Expert"),
    (40, "📚 Connaisseur"),
    (20, "🌱 Amateur"),
    (0, "👶 Débutant")
]

def load_xp():
    if os.path.exists(XP_FILE):
        with open(XP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_xp(data):
    with open(XP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_xp(user_id, amount):
    data = load_xp()
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = 0
    data[user_id] += amount
    save_xp(data)

def get_xp(user_id):
    data = load_xp()
    return data.get(str(user_id), 0)

def get_rank(user_id):
    data = load_xp()
    sorted_users = sorted(data.items(), key=lambda x: x[1], reverse=True)
    for i, (uid, _) in enumerate(sorted_users, 1):
        if uid == str(user_id):
            return i
    return None

def get_title(score):
    for threshold, title in TITLES:
        if score >= threshold:
            return title
    return "👶 Débutant"

def get_top_users(limit=10):
    data = load_xp()
    return sorted(data.items(), key=lambda x: x[1], reverse=True)[:limit]

def reset_monthly_scores():
    data = load_xp()
    if not data:
        return

    winner_id, winner_score = max(data.items(), key=lambda x: x[1])
    now = datetime.datetime.now()
    month_key = f"{now.year}-{now.month:02d}"

    winners = {}
    if os.path.exists(WINNERS_FILE):
        with open(WINNERS_FILE, "r", encoding="utf-8") as f:
            winners = json.load(f)

    winners[month_key] = {
        "user_id": winner_id,
        "score": winner_score
    }

    with open(WINNERS_FILE, "w", encoding="utf-8") as f:
        json.dump(winners, f, ensure_ascii=False, indent=2)

    save_xp({})  # reset

def get_days_until_reset():
    now = datetime.datetime.now()
    next_month = now.replace(day=28) + datetime.timedelta(days=4)
    reset_date = next_month.replace(day=1)
    return (reset_date - now).days

def get_last_winner():
    if os.path.exists(WINNERS_FILE):
        with open(WINNERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not data:
                return None
            last_key = sorted(data.keys())[-1]
            return data[last_key]
    return None
