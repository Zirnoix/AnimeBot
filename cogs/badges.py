# modules/badges.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional

# Badges à paliers (compte -> palier)
# thresholds = seuils pour atteindre chaque palier
# icons = rendu visuel du badge par palier (tu pourras remplacer par des URLs d’images)
BADGES: Dict[str, Dict] = {
    "guessgenre": {
        "name": "GuessGenre",
        "desc": "Bonnes réponses au mini-jeu GuessGenre.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["🟩", "🟦", "🟨", "🟥"],
        "source": "mini:guessgenre",
    },
    "guessyear": {
        "name": "GuessYear",
        "desc": "Bonnes réponses au mini-jeu GuessYear.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["📅", "📅⭐", "📅💠", "📅👑"],
        "source": "mini:guessyear",
    },
    "animequiz": {
        "name": "AnimeQuiz (Solo)",
        "desc": "Bonnes réponses au quiz image solo.",
        "thresholds": [50, 100, 250, 500],
        "icons": ["🔰", "🎖️", "🏆", "👑"],
        "source": "mini:animequiz",  # on incrémente déjà ce compteur dans ton code
    },
    "animequizmulti": {
        "name": "AnimeQuiz (Multi)",
        "desc": "Parties terminées en quiz multi.",
        "thresholds": [25, 75, 150, 300],
        "icons": ["🎯", "🥉", "🥈", "🥇"],
        "source": "mini:animequizmulti",  # incrémente quand une partie multi se termine
    },
    "streak": {
        "name": "Streak",
        "desc": "Série de check-ins quotidiens.",
        "thresholds": [7, 30, 100, 365],
        "icons": ["🔥", "💥", "⚡", "🌟"],
        "source": "streak:days",
    },
}

def evaluate_tier(count: int, thresholds: List[int]) -> Tuple[int, Optional[int]]:
    """
    Retourne (tier_index, next_threshold)
    - tier_index ∈ {-1,0,1,2,3} où -1 = aucun palier atteint
    - next_threshold = prochain seuil (ou None si max atteint)
    """
    tier = -1
    for i, t in enumerate(thresholds):
        if count >= t:
            tier = i
        else:
            return tier, t
    return tier, None
