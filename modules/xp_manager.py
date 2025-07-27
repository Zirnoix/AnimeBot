import json
import os

SCORES_FILE = "quiz_scores.json"


def load_scores():
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_scores(scores):
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)


def add_score(user_id, amount):
    scores = load_scores()
    uid = str(user_id)
    scores[uid] = scores.get(uid, 0) + amount
    save_scores(scores)


def get_score(user_id):
    scores = load_scores()
    return scores.get(str(user_id), 0)

