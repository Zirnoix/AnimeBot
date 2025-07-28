import random
import json
import os
from datetime import datetime, timedelta

QUIZ_DATA_PATH = "data/quiz_data.json"
RESET_FILE_PATH = "data/quiz_reset.json"

def fetch_quiz_question():
    if not os.path.exists(QUIZ_DATA_PATH):
        return None

    with open(QUIZ_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    question = random.choice(data)
    return question

def get_days_until_reset():
    if not os.path.exists(RESET_FILE_PATH):
        return "?"
    
    with open(RESET_FILE_PATH, "r") as f:
        data = json.load(f)

    reset_date_str = data.get("reset_date")
    if not reset_date_str:
        return "?"

    reset_date = datetime.strptime(reset_date_str, "%Y-%m-%d")
    today = datetime.now()
    delta = reset_date - today

    return max(0, delta.days)

def get_title(score):
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

def update_score(user_id, score, scores_file="data/quiz_scores.json"):
    if not os.path.exists(scores_file):
        scores = {}
    else:
        with open(scores_file, "r") as f:
            scores = json.load(f)

    user_id = str(user_id)
    scores[user_id] = scores.get(user_id, 0) + score

    with open(scores_file, "w") as f:
        json.dump(scores, f, indent=4)
