from __future__ import annotations
from typing import Dict, List, Tuple, Optional

# Catégories d’affichage (/mybadges, onglet trophées) — ordre fixe
BADGE_CATEGORY_ORDER: tuple[str, ...] = (
    "profil",
    "quiz",
    "guess",
    "communaute",
    "anilist",
    "temps",
)

BADGE_SECTION_TITLE_FR: dict[str, str] = {
    "profil": "Profil & engagement",
    "quiz": "Quiz & duels",
    "guess": "Devinettes",
    "communaute": "Communauté",
    "anilist": "AniList",
    "temps": "Horaires",
    "autre": "Autres",
}


def tier_name_fr(tier_index: int) -> str:
    """Nom du palier (0 = premier palier débloqué)."""
    names = ("Initié", "Confirmé", "Vétéran", "Élite", "Mythe")
    if 0 <= tier_index < len(names):
        return names[tier_index]
    return f"Palier {tier_index + 1}"


def iter_badges_sorted() -> List[tuple[str, Dict]]:
    """Itère les badges dans l’ordre d’affichage (catégorie puis nom)."""
    items = list(BADGES.items())

    def sort_key(item: tuple[str, Dict]) -> tuple[int, str]:
        _bid, spec = item
        cat = spec.get("category", "autre")
        try:
            ci = BADGE_CATEGORY_ORDER.index(cat)
        except ValueError:
            ci = len(BADGE_CATEGORY_ORDER)
        return (ci, str(spec.get("name", _bid)).lower())

    return sorted(items, key=sort_key)


# Badges à paliers — sources : mini:* (mini_scores.json), streak:*, anilist:*, time:*, mini_sum:*
BADGES: Dict[str, Dict] = {
    # --- Profil & engagement ---
    "serie": {
        "name": "Rythme quotidien",
        "desc": "Jours consécutifs avec /checkin (série active).",
        "thresholds": [7, 30, 100, 365],
        "icons": ["🔥", "💢", "⚡", "✨"],
        "source": "streak:days",
        "category": "profil",
    },
    "checkins_total": {
        "name": "Fidèle au bot",
        "desc": "Nombre total de check-ins /checkin effectués.",
        "thresholds": [10, 50, 150, 400],
        "icons": ["📒", "📔", "📕", "📗"],
        "source": "mini:checkin",
        "category": "profil",
    },
    "missions": {
        "name": "Missionnaire",
        "desc": "Missions quotidiennes terminées (récompense XP).",
        "thresholds": [5, 15, 40, 80, 150],
        "icons": ["🎯", "🎖️", "🏅", "🥇", "🏆"],
        "source": "mini:mission_completed",
        "category": "profil",
    },
    "carte": {
        "name": "Carte de membre",
        "desc": "Fois où tu as ouvert ta /mycard.",
        "thresholds": [5, 25, 75, 200],
        "icons": ["🪪", "🃏", "🎴", "🎫"],
        "source": "mini:mycard_visits",
        "category": "profil",
    },

    # --- Quiz & duels ---
    "quiz_solo": {
        "name": "Œil d’aigle",
        "desc": "Bonnes réponses au quiz image solo (/animequiz).",
        "thresholds": [50, 100, 250, 500],
        "icons": ["👁️", "🔍", "🔭", "🦅"],
        "source": "mini:animequiz",
        "category": "quiz",
    },
    "quiz_multi": {
        "name": "Salle d’arcade",
        "desc": "Parties de quiz multi terminées (/animequizmulti).",
        "thresholds": [10, 25, 75, 150, 300],
        "icons": ["🕹️", "🎮", "🎰", "👾", "🥇"],
        "source": "mini:animequizmulti",
        "category": "quiz",
    },
    "duelliste": {
        "name": "Duelliste",
        "desc": "Duels lancés avec /duel.",
        "thresholds": [5, 15, 30, 50],
        "icons": ["🎪", "🤺", "⚔️", "🏟️"],
        "source": "mini:duel",
        "category": "quiz",
    },
    "vainqueur": {
        "name": "Vainqueur",
        "desc": "Manches de duel remportées.",
        "thresholds": [5, 15, 30, 50],
        "icons": ["🥉", "🥈", "🥇", "💎"],
        "source": "mini:duel_victory",
        "category": "quiz",
    },
    "podium_mois": {
        "name": "Podium du mois",
        "desc": "Podiums sur le classement mensuel du quiz (1ʳᵉ, 2ᵉ ou 3ᵉ place).",
        "thresholds": [1, 3, 6, 12, 24],
        "icons": ["🌸", "🌺", "🌻", "🌷", "💐"],
        "source": "mini_sum:quiz_month_1st,quiz_month_2nd,quiz_month_3rd",
        "category": "quiz",
    },

    # --- Devinettes ---
    "guess_genre": {
        "name": "Connaisseur de genres",
        "desc": "Bonnes réponses au Guess genre.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["🎭", "🎪", "🎬", "🎞️"],
        "source": "mini:guessgenre",
        "category": "guess",
    },
    "guess_annee": {
        "name": "Chronologue",
        "desc": "Bonnes réponses au Guess année.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["📜", "📆", "🗓️", "📅"],
        "source": "mini:guessyear",
        "category": "guess",
    },
    "guess_episodes": {
        "name": "Compteur d’épisodes",
        "desc": "Bonnes réponses au Guess nombre d’épisodes.",
        "thresholds": [25, 50, 100, 200],
        "icons": ["1️⃣", "🔢", "#️⃣", "🔟"],
        "source": "mini:guessepisodes",
        "category": "guess",
    },
    "guess_perso": {
        "name": "Tête chercheuse",
        "desc": "Bonnes réponses au Guess personnage (image).",
        "thresholds": [15, 40, 80, 150],
        "icons": ["🧩", "🎭", "🎪", "🎨"],
        "source": "mini:guesscharacter",
        "category": "guess",
    },
    "higher_lower": {
        "name": "Popularité",
        "desc": "Parties gagnées au Higher / Lower.",
        "thresholds": [20, 50, 100, 200],
        "icons": ["📈", "📊", "📉", "🎯"],
        "source": "mini:higherlower",
        "category": "guess",
    },
    "guess_op": {
        "name": "Oreille musicale",
        "desc": "Victoires au Guess opening.",
        "thresholds": [10, 30, 60, 120],
        "icons": ["🎼", "🎹", "🎸", "🎤"],
        "source": "mini:guessop",
        "category": "guess",
    },
    "guess_silhouette": {
        "name": "Silhouette",
        "desc": "Victoires au Guess qui est-ce (image floutée).",
        "thresholds": [5, 20, 45, 100],
        "icons": ["👤", "👥", "🎭", "🌟"],
        "source": "mini:guesswho",
        "category": "guess",
    },

    # --- Communauté (raid, chaînes) ---
    "boss_raid": {
        "name": "Lame de raid",
        "desc": "Dégâts infligés au boss lors des Boss Raid (tous combats confondus).",
        "thresholds": [50, 250, 800, 2500],
        "icons": ["🗡️", "⚔️", "🛡️", "🏰"],
        "source": "mini:bossraid",
        "category": "communaute",
    },
    "chainquiz": {
        "name": "Marathon quiz",
        "desc": "Chain quiz terminés (bonne réponse qui enchaîne une manche).",
        "thresholds": [3, 12, 30, 75],
        "icons": ["⛓️", "🔗", "🧷", "🏁"],
        "source": "mini:chainquiz",
        "category": "communaute",
    },

    # --- AniList & horaires ---
    "collection": {
        "name": "Collectionneur",
        "desc": "Animes marqués comme complétés sur AniList (compte lié).",
        "thresholds": [50, 150, 300, 600, 1000],
        "icons": ["📚", "📖", "📘", "📙", "📕"],
        "source": "anilist:completed",
        "category": "anilist",
    },
    "earlybird": {
        "name": "Lève-tôt",
        "desc": "Parties lancées entre 6h et 10h (heure du bot).",
        "thresholds": [15, 50, 150],
        "icons": ["🌅", "☀️", "🌄"],
        "source": "time:morning",
        "category": "temps",
    },
    "nightowl": {
        "name": "Oiseau de nuit",
        "desc": "Parties lancées entre minuit et 4h (heure du bot).",
        "thresholds": [15, 50, 150],
        "icons": ["🌙", "🦉", "🌌"],
        "source": "time:night",
        "category": "temps",
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
