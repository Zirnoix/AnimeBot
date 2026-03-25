from __future__ import annotations
from typing import Dict, List, Tuple, Optional

# Badges à paliers — sources : mini:* (mini_scores.json), streak:*, anilist:*, time:*, mini_sum:* (somme de clés mini)
BADGES: Dict[str, Dict] = {
    # --- Engagement & profil ---
    "serie": {
        "name": "Rythme quotidien",
        "desc": "Jours consécutifs avec /checkin (série active).",
        "thresholds": [7, 30, 100, 365],
        "icons": ["🔥", "💥", "⚡", "🌟"],
        "source": "streak:days",
    },
    "checkins_total": {
        "name": "Fidèle au bot",
        "desc": "Nombre total de check-ins /checkin effectués.",
        "thresholds": [10, 50, 150, 400],
        "icons": ["📅", "📅⭐", "📅💠", "📅👑"],
        "source": "mini:checkin",
    },
    "missions": {
        "name": "Missionnaire",
        "desc": "Missions quotidiennes terminées (récompense XP).",
        "thresholds": [5, 15, 40, 80, 150],
        "icons": ["🎯", "🎯⭐", "🎯💠", "🎯👑", "🏅"],
        "source": "mini:mission_completed",
    },
    "carte": {
        "name": "Carte de membre",
        "desc": "Fois où tu as ouvert ta /mycard.",
        "thresholds": [5, 25, 75, 200],
        "icons": ["🪪", "🪪⭐", "🪪💠", "🪪👑"],
        "source": "mini:mycard_visits",
    },

    # --- Quiz & duels ---
    "quiz_solo": {
        "name": "Œil d’aigle",
        "desc": "Bonnes réponses au quiz image solo (/animequiz).",
        "thresholds": [50, 100, 250, 500],
        "icons": ["🔰", "🎖️", "🏆", "👑"],
        "source": "mini:animequiz",
    },
    "quiz_multi": {
        "name": "Salle d’arcade",
        "desc": "Parties de quiz multi terminées (/animequizmulti).",
        "thresholds": [10, 25, 75, 150, 300],
        "icons": ["🎯", "🥉", "🥈", "🥇", "👑"],
        "source": "mini:animequizmulti",
    },
    "duelliste": {
        "name": "Duelliste",
        "desc": "Duels lancés avec /duel.",
        "thresholds": [5, 15, 30, 50],
        "icons": ["⚔️", "⚔️⭐", "⚔️💠", "⚔️👑"],
        "source": "mini:duel",
    },
    "vainqueur": {
        "name": "Vainqueur",
        "desc": "Manches de duel remportées.",
        "thresholds": [5, 15, 30, 50],
        "icons": ["🏅", "🏅⭐", "🏅💠", "🏅👑"],
        "source": "mini:duel_victory",
    },
    "podium_mois": {
        "name": "Podium du mois",
        "desc": "Podiums sur le classement mensuel du quiz (1ʳᵉ, 2ᵉ ou 3ᵉ place).",
        "thresholds": [1, 3, 6, 12, 24],
        "icons": ["🥇", "🥇⭐", "🥇💠", "🥇👑", "💎"],
        "source": "mini_sum:quiz_month_1st,quiz_month_2nd,quiz_month_3rd",
    },

    # --- Devinettes ---
    "guess_genre": {
        "name": "Connaisseur de genres",
        "desc": "Bonnes réponses au Guess genre.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["🎭", "🎭⭐", "🎭💠", "🎭👑"],
        "source": "mini:guessgenre",
    },
    "guess_annee": {
        "name": "Chronologue",
        "desc": "Bonnes réponses au Guess année.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["📅", "📅⭐", "📅💠", "📅👑"],
        "source": "mini:guessyear",
    },
    "guess_episodes": {
        "name": "Compteur d’épisodes",
        "desc": "Bonnes réponses au Guess nombre d’épisodes.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["🔢", "🔢⭐", "🔢💠", "🔢👑"],
        "source": "mini:guessepisodes",
    },
    "guess_perso": {
        "name": "Tête chercheuse",
        "desc": "Bonnes réponses au Guess personnage.",
        "thresholds": [15, 40, 80, 150],
        "icons": ["🧩", "🧩⭐", "🧩💠", "🧩👑"],
        "source": "mini:guesscharacter",
    },
    "higher_lower": {
        "name": "Popularité",
        "desc": "Parties gagnées au Higher / Lower.",
        "thresholds": [20, 50, 100, 200],
        "icons": ["📊", "📊⭐", "📊💠", "📊👑"],
        "source": "mini:higherlower",
    },
    "guess_op": {
        "name": "Oreille musicale",
        "desc": "Victoires au Guess opening.",
        "thresholds": [10, 30, 60, 120],
        "icons": ["🎵", "🎵⭐", "🎵💠", "🎵👑"],
        "source": "mini:guessop",
    },

    # --- AniList & horaires ---
    "collection": {
        "name": "Collectionneur",
        "desc": "Animes marqués comme complétés sur AniList (compte lié).",
        "thresholds": [50, 150, 300, 600, 1000],
        "icons": ["📚", "📚⭐", "📚💠", "📚👑", "📚💎"],
        "source": "anilist:completed",
    },
    "earlybird": {
        "name": "Lève-tôt",
        "desc": "Parties lancées entre 6h et 10h (heure du bot).",
        "thresholds": [15, 50, 150],
        "icons": ["🌅", "🌅⭐", "🌅💠"],
        "source": "time:morning",
    },
    "nightowl": {
        "name": "Oiseau de nuit",
        "desc": "Parties lancées entre minuit et 4h (heure du bot).",
        "thresholds": [15, 50, 150],
        "icons": ["🌙", "🌙⭐", "🌙💠"],
        "source": "time:night",
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
