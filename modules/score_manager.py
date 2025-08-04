# modules/score_manager.py

import json
import os

QUIZ_SCORES_FILE = "data/quiz_scores.json"
GAME_SCORES_FILE = "data/game_scores.json"
DUELS_FILE = "data/duel_scores.json"
GUESS_FILE = "data/guess_scores.json"

# --- UTILS JSON ---

def load_scores(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_scores(scores, file_path):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

# === GESTION QUIZ ===

def load_quiz_scores():
    if os.path.exists(QUIZ_SCORES_FILE):
        with open(QUIZ_SCORES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_quiz_scores(scores):
    with open(QUIZ_SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

def update_quiz_score(user_id, points):
    scores = load_quiz_scores()
    scores[user_id] = scores.get(user_id, 0) + points
    save_quiz_scores(scores)

def get_quiz_score(user_id):
    return load_quiz_scores().get(user_id, 0)

# --- DUELS ---

def update_duel_stats(winner_id: str, loser_id: str):
    stats = load_scores(DUELS_FILE)

    if winner_id not in stats:
        stats[winner_id] = {"wins": 0, "losses": 0}
    if loser_id not in stats:
        stats[loser_id] = {"wins": 0, "losses": 0}

    stats[winner_id]["wins"] += 1
    stats[loser_id]["losses"] += 1

    save_scores(stats, DUELS_FILE)

def get_duel_stats(user_id: str):
    stats = load_scores(DUELS_FILE)
    return stats.get(user_id, {"wins": 0, "losses": 0})

# === GESTION MINI-JEUX "GUESS" ===

def load_game_scores():
    if os.path.exists(GAME_SCORES_FILE):
        with open(GAME_SCORES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_game_scores(scores):
    with open(GAME_SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

def update_game_score(user_id, game_mode, points):
    scores = load_game_scores()
    if user_id not in scores:
        scores[user_id] = {}
    scores[user_id][game_mode] = scores[user_id].get(game_mode, 0) + points
    save_game_scores(scores)

def get_user_scores(user_id):
    scores = load_game_scores()
    return scores.get(user_id, {})
