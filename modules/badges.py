from __future__ import annotations
from typing import Dict, List, Tuple, Optional

# Badges à paliers
BADGES: Dict[str, Dict] = {
    # === Mini-jeux existants ===
    "guessgenre": {
        "name": "GuessGenre",
        "desc": "Bonnes réponses au mini-jeu GuessGenre.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["🎭", "🎭⭐", "🎭💠", "🎭👑"],
        "icons_custom": ["ab_guessgenre_1","ab_guessgenre_2","ab_guessgenre_3","ab_guessgenre_4"],
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
        "source": "mini:animequiz",
    },
    "animequizmulti": {
        "name": "AnimeQuiz (Multi)",
        "desc": "Parties terminées en quiz multi.",
        "thresholds": [25, 75, 150, 300],
        "icons": ["🎯", "🥉", "🥈", "🥇"],
        "source": "mini:animequizmulti",
    },
    "streak": {
        "name": "Streak",
        "desc": "Série de check-ins quotidiens.",
        "thresholds": [7, 30, 100, 365],
        "icons": ["🔥", "💥", "⚡", "🌟"],
        "source": "streak:days",
    },

    # === Nouveaux badges (validés ensemble) ===
    "earlybird": {
        "name": "Early Bird",
        "desc": "A joué tôt le matin (6h-10h).",
        "thresholds": [15, 50, 150],
        "icons": ["🌅", "🌅⭐", "🌅💠"],
        "source": "time:morning",
    },
    "nightowl": {
        "name": "Night Owl",
        "desc": "A joué tard dans la nuit (0h-4h).",
        "thresholds": [15, 50, 150],
        "icons": ["🌙", "🌙⭐", "🌙💠"],
        "source": "time:night",
    },
    "opchallenger": {
        "name": "OP Challenger",
        "desc": "Victoires au mini-jeu GuessOP.",
        "thresholds": [10, 30, 60, 120],
        "icons": ["🎵", "🎵⭐", "🎵💠", "🎵👑"],
        "source": "mini:guessop",
    },
    "versusmaster": {
        "name": "Versus Master",
        "desc": "A battu plusieurs joueurs différents en duel quiz.",
        "thresholds": [5, 15, 30, 50],
        "icons": ["⚔️", "⚔️⭐", "⚔️💠", "⚔️👑"],
        "source": "mini:duel",
    },

    # === AniList et commandes ===
    "planningaddict": {
        "name": "Planning Addict",
        "desc": "A consulté le planning des sorties.",
        "thresholds": [10, 50, 100],
        "icons": ["🗓️", "🗓️⭐", "🗓️💠"],
        "source": "command:planning",
        "hidden": True,  # Badge caché
    },
    "decouvreur": {
        "name": "Découvreur",
        "desc": "A utilisé la commande Découverte.",
        "thresholds": [10, 50, 100],
        "icons": ["🔍", "🔍⭐", "🔍💠"],
        "source": "command:decouverte",
        "hidden": True,  # Badge caché
    },
    "mylistcollector": {
        "name": "MyList Collector",
        "desc": "A atteint un nombre d’animes dans sa liste AniList.",
        "thresholds": [100, 300, 500, 1000],
        "icons": ["📚", "📚⭐", "📚💠","📚👑"],
        "source": "anilist:completed",
        "hidden": True,  # Badge caché
    },

    # === Spéciaux ===
    "betatester": {
        "name": "Beta Tester",
        "desc": "A participé à la bêta du bot.",
        "thresholds": [1],
        "icons": ["🧪"],
        "source": "special:time",
    },
    "devotedotaku": {
        "name": "Devoted Otaku",
        "desc": "A été actif 365 jours dans l’année.",
        "thresholds": [365],
        "icons": ["🔥"],
        "source": "streak:year",
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
