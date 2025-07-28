# modules/database.py

import json
import os
from datetime import datetime, timedelta

SCORES_FILE = "data/quiz_scores.json"
WINNER_FILE = "data/monthly_winner.json"

def load_scores():
    if not os.path.exists(SCORES_FILE):
        return {}
    with open(SCORES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_scores(scores):
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

def add_score(user_id, amount):
    scores = load_scores()
    user_id = str(user_id)
    scores[user_id] = scores.get(user_id, 0) + amount
    save_scores(scores)

def get_monthly_winner():
    if not os.path.exists(WINNER_FILE):
        return None
    with open(WINNER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def set_monthly_winner(winner_id, score):
    with open(WINNER_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "winner_id": winner_id,
            "score": score,
            "date": datetime.now().strftime("%Y-%m-%d")
        }, f, ensure_ascii=False, indent=2)

def reset_monthly_scores():
    scores = load_scores()
    if not scores:
        return

    top_user = max(scores.items(), key=lambda x: x[1])
    set_monthly_winner(top_user[0], top_user[1])
    save_scores({})  # reset scores

def days_until_next_month():
    now = datetime.now()
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (next_month - now).days
