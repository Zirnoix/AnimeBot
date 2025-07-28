# modules/database.py

import json
import os

DB_FOLDER = "data"
DB_FILE = os.path.join(DB_FOLDER, "scores.json")
MONTHLY_WINNER_FILE = os.path.join(DB_FOLDER, "monthly_winner.json")

def ensure_data_files():
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

    if not os.path.exists(MONTHLY_WINNER_FILE):
        with open(MONTHLY_WINNER_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def load_scores():
    ensure_data_files()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_scores(scores):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

def add_score(user_id, points):
    scores = load_scores()
    user_id = str(user_id)
    scores[user_id] = scores.get(user_id, 0) + points
    save_scores(scores)

def reset_monthly_scores():
    scores = load_scores()
    if not scores:
        return None  # Aucun score à enregistrer

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    winner_id, top_score = sorted_scores[0]

    save_monthly_winner(winner_id, top_score)

    # Réinitialiser les scores
    save_scores({})
    return winner_id, top_score

def get_monthly_winner():
    ensure_data_files()
    with open(MONTHLY_WINNER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_monthly_winner(user_id, score):
    with open(MONTHLY_WINNER_FILE, "w", encoding="utf-8") as f:
        json.dump({"winner": user_id, "score": score}, f, ensure_ascii=False, indent=2)
