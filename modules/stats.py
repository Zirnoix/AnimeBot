import json
import os
from datetime import datetime, timedelta

SCORES_FILE = "data/quiz_scores.json"
WINNERS_FILE = "data/quiz_winners.json"

def load_scores():
    if not os.path.exists(SCORES_FILE):
        return {}
    with open(SCORES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_scores(scores):
    os.makedirs(os.path.dirname(SCORES_FILE), exist_ok=True)
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

def add_score(user_id, points):
    scores = load_scores()
    scores[str(user_id)] = scores.get(str(user_id), 0) + points
    save_scores(scores)

def reset_monthly_scores():
    scores = load_scores()
    if not scores:
        return None

    winner_id = max(scores, key=scores.get)
    winner_score = scores[winner_id]

    os.makedirs(os.path.dirname(WINNERS_FILE), exist_ok=True)
    if os.path.exists(WINNERS_FILE):
        with open(WINNERS_FILE, "r", encoding="utf-8") as f:
            winners = json.load(f)
    else:
        winners = {}

    now = datetime.utcnow()
    last_month = now.replace(day=1) - timedelta(days=1)
    key = last_month.strftime("%B %Y")

    winners[key] = {
        "user_id": winner_id,
        "score": winner_score
    }

    with open(WINNERS_FILE, "w", encoding="utf-8") as f:
        json.dump(winners, f, ensure_ascii=False, indent=2)

    save_scores({})  # reset scores
    return winner_id, winner_score

def get_leaderboard(top_n=10):
    scores = load_scores()
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_scores[:top_n]

def get_user_rank(user_id):
    scores = load_scores()
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for i, (uid, score) in enumerate(sorted_scores, 1):
        if uid == str(user_id):
            return i, score
    return None, 0

def get_days_until_reset():
    now = datetime.utcnow()
    next_month = now.replace(day=28) + timedelta(days=4)
    first_day_next_month = next_month.replace(day=1)
    return (first_day_next_month - now).days

def get_last_month_winner():
    if not os.path.exists(WINNERS_FILE):
        return None

    with open(WINNERS_FILE, "r", encoding="utf-8") as f:
        winners = json.load(f)

    if not winners:
        return None

    last_key = sorted(winners.keys())[-1]
    return last_key, winners[last_key]
