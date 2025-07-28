import json
import os
from datetime import datetime

XP_FILE = "quiz_scores.json"


def load_scores():
    if not os.path.exists(XP_FILE):
        return {}
    with open(XP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_scores(scores):
    with open(XP_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)


def add_score(user_id: int, points: int = 1):
    scores = load_scores()
    str_id = str(user_id)
    if str_id not in scores:
        scores[str_id] = 0
    scores[str_id] += points
    save_scores(scores)


def get_score(user_id: int) -> int:
    return load_scores().get(str(user_id), 0)


def get_leaderboard():
    scores = load_scores()
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def get_title(score: int) -> str:
    if score >= 100:
        return "🌌 Légende"
    elif score >= 80:
        return "🔥 Champion"
    elif score >= 60:
        return "🎯 Expert"
    elif score >= 40:
        return "📚 Connaisseur"
    elif score >= 20:
        return "🌱 Amateur"
    else:
        return "👶 Débutant"


def should_reset_scores():
    today = datetime.today()
    return today.day == 1


def reset_monthly_scores():
    if should_reset_scores():
        scores = load_scores()
        leaderboard = get_leaderboard()
        if leaderboard:
            top_user = leaderboard[0][0]
            with open("last_winner.txt", "w") as f:
                f.write(top_user)
        save_scores({})


def get_last_winner():
    if os.path.exists("last_winner.txt"):
        with open("last_winner.txt", "r") as f:
            return f.read()
    return None


def get_days_until_reset():
    today = datetime.today()
    next_month = today.replace(day=28) + timedelta(days=4)
    first_next_month = next_month.replace(day=1)
    return (first_next_month - today).days
