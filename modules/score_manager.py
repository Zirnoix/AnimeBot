import json
import os
from datetime import datetime

SCORES_FILE = "scores.json"


def load_scores():
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_scores(scores):
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)


def add_quiz_point(user_id):
    scores = load_scores()
    user_id = str(user_id)
    scores[user_id] = scores.get(user_id, 0) + 1
    save_scores(scores)


def get_top_scores(limit=10):
    scores = load_scores()
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_scores[:limit]


def reset_monthly_scores():
    if os.path.exists(SCORES_FILE):
        os.rename(SCORES_FILE, f"scores_{datetime.now().strftime('%Y_%m')}.json")


def get_user_rank(user_id):
    scores = load_scores()
    user_id = str(user_id)
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for rank, (uid, _) in enumerate(sorted_scores, start=1):
        if uid == user_id:
            return rank
    return None
