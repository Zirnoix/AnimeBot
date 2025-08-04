# modules/score_manager.py

import json
import os

SCORES_FILE = "data/quiz_scores.json"
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

# --- QUIZ CLASSIQUE ---

def update_quiz_score(user_id: str, score: int):
    scores = load_scores(SCORES_FILE)
    scores[user_id] = scores.get(user_id, 0) + score
    save_scores(scores, SCORES_FILE)

def get_quiz_score(user_id: str) -> int:
    return load_scores(SCORES_FILE).get(user_id, 0)

def get_quiz_leaderboard(limit: int = 10):
    scores = load_scores(SCORES_FILE)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

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

# --- GUESS GAMES (guessyear, guessgenre, etc.) ---

def get_user_scores(user_id):
    """Retourne tous les scores d’un utilisateur sous forme de dict"""
    if not os.path.exists(SCORE_FILE):
        return {}
    with open(SCORE_FILE, "r", encoding="utf-8") as f:
        scores = json.load(f)
    return scores.get(user_id, {})

def update_guess_score(user_id: str, game_type: str, points: int):
    """
    Ajoute des points à un mini-jeu spécifique.
    game_type: "guessyear", "guessgenre", "episodes", etc.
    """
    scores = load_scores(GUESS_FILE)
    if user_id not in scores:
        scores[user_id] = {}
    scores[user_id][game_type] = scores[user_id].get(game_type, 0) + points
    save_scores(scores, GUESS_FILE)

def get_user_guess_scores(user_id: str):
    scores = load_scores(GUESS_FILE)
    return scores.get(user_id, {})

def get_total_guess_score(user_id: str):
    scores = get_user_guess_scores(user_id)
    return sum(scores.values())
