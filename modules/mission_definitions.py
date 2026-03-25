"""
Définitions des missions quotidiennes — source unique (libellé, commandes, objectif, aide).
Le tirage au sort et les hints sont dérivés de cette liste.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, FrozenSet


@dataclass(frozen=True)
class MissionDef:
    key: str
    label: str
    commands: FrozenSet[str]
    goal: int
    difficulty: str  # EASY | MEDIUM | HARD
    distinct: bool
    hint: str


def _fs(*items: str) -> FrozenSet[str]:
    return frozenset(items)


MISSION_DEFINITIONS: List[MissionDef] = [
    MissionDef(
        "use_next",
        "Utilise `/next` ou `/monnext` aujourd'hui",
        _fs("next", "monnext"),
        1,
        "EASY",
        False,
        "Lance **`/next`** ou **`/monnext`** une fois dans ce serveur.",
    ),
    MissionDef(
        "use_planning",
        "Consulte ton planning (`/planning` ou `/monplanning`)",
        _fs("planning", "monplanning"),
        1,
        "EASY",
        False,
        "Ouvre **`/planning`** ou **`/monplanning`** pour consulter les sorties.",
    ),
    MissionDef(
        "use_3_tracking",
        "Utilise 3 commandes de suivi **différentes** (`/next`, `/planning`, `/monplanning`, `/monnext`)",
        _fs("next", "planning", "monplanning", "monnext"),
        3,
        "MEDIUM",
        True,
        "Enchaîne **3 commandes différentes** parmi `/next`, `/planning`, `/monplanning`, `/monnext` (sans répéter la même).",
    ),
    MissionDef(
        "duel_initiate",
        "Lance un duel avec `/duel`",
        _fs("duel"),
        1,
        "EASY",
        False,
        "Lance un duel avec **`/duel @quelqu’un`** (la partie doit démarrer).",
    ),
    MissionDef(
        "duel_win",
        "Remporte un duel aujourd’hui",
        _fs("_custom:duel_win"),
        1,
        "HARD",
        False,
        "Remporte **au moins une manche** d’un duel aujourd’hui (événement en arrière-plan).",
    ),
    MissionDef(
        "quiz_play",
        "Participe à un quiz solo avec `/animequiz`",
        _fs("animequiz"),
        1,
        "EASY",
        False,
        "Joue **`/animequiz`** puis réponds (partie solo).",
    ),
    MissionDef(
        "quiz_win",
        "Gagne un quiz aujourd’hui (solo ou multi)",
        _fs("_custom:quiz_win", "_custom:quiz_solo_ok"),
        1,
        "MEDIUM",
        False,
        "Réponds correctement à un quiz **aujourd’hui** (solo ou multi ≥ 50%).",
    ),
    MissionDef(
        "quiz_multi_done",
        "Termine une partie de `/animequizmulti`",
        _fs("animequizmulti"),
        1,
        "MEDIUM",
        False,
        "Lance **`/animequizmulti`** et joue jusqu’à l’écran de fin de partie.",
    ),
    MissionDef(
        "level_up",
        "Passe un niveau global (XP) aujourd’hui",
        _fs("_custom:level_up"),
        1,
        "HARD",
        False,
        "Passe **un niveau** global (XP) dans la journée — continue à jouer / quiz.",
    ),
    MissionDef(
        "use_checkin",
        "Fais ton `/checkin` du jour",
        _fs("checkin"),
        1,
        "EASY",
        False,
        "Utilise **`/checkin`** (ou **`/daily`**) pour valider ta présence du jour.",
    ),
    MissionDef(
        "use_mycard",
        "Ouvre ta carte avec `/mycard`",
        _fs("mycard"),
        1,
        "EASY",
        False,
        "Ouvre **`/mycard`** pour afficher ta carte de membre.",
    ),
    MissionDef(
        "use_mystats",
        "Consulte tes stats AniList avec `/mystats`",
        _fs("mystats"),
        1,
        "EASY",
        False,
        "Affiche tes stats AniList avec **`/mystats`** (compte lié requis).",
    ),
    MissionDef(
        "use_decouverte",
        "Utilise `/decouverte` (anime au hasard)",
        _fs("decouverte"),
        1,
        "EASY",
        False,
        "Tire un anime au hasard avec **`/decouverte`**.",
    ),
    MissionDef(
        "use_higherlower",
        "Joue une partie de `/higherlower`",
        _fs("higherlower"),
        1,
        "MEDIUM",
        False,
        "Joue une manche de **`/higherlower`** jusqu’à la fin.",
    ),
    MissionDef(
        "use_help",
        "Consulte la `/help` du bot",
        _fs("help"),
        1,
        "EASY",
        False,
        "Affiche l’aide avec **`/help`**.",
    ),
    MissionDef(
        "use_myrank",
        "Affiche ton `/myrank`",
        _fs("myrank"),
        1,
        "EASY",
        False,
        "Consulte ton classement avec **`/myrank`**.",
    ),
    MissionDef(
        "use_quiztop",
        "Consulte le `/quiztop`",
        _fs("quiztop"),
        1,
        "EASY",
        False,
        "Ouvre le classement mensuel avec **`/quiztop`**.",
    ),
    MissionDef(
        "use_reminder",
        "Utilise `/reminder` ou `/setalert`",
        _fs("reminder", "setalert"),
        1,
        "EASY",
        False,
        "Configure ou consulte ton récap avec **`/reminder`** ou **`/setalert`**.",
    ),
    MissionDef(
        "use_track",
        "Utilise `/track list` ou `/track add`",
        _fs("track list", "track add"),
        1,
        "EASY",
        False,
        "Utilise **`/track list`** ou **`/track add`** (suivi d’animes).",
    ),
    MissionDef(
        "use_minijeux",
        "Ouvre le menu `/minijeux`",
        _fs("minijeux"),
        1,
        "EASY",
        False,
        "Ouvre le hub **`/minijeux`**.",
    ),
    MissionDef(
        "use_guessop",
        "Lance une partie de `/guessop`",
        _fs("guessop"),
        1,
        "MEDIUM",
        False,
        "Lance une partie de **`/guessop`** (opening).",
    ),
    MissionDef(
        "use_stats",
        "Consulte les stats d’un pseudo avec `/stats`",
        _fs("stats"),
        1,
        "EASY",
        False,
        "Consulte les stats d’un pseudo avec **`/stats <pseudo>`**.",
    ),
    MissionDef(
        "guess_two_kinds",
        "Joue à **2** devinettes **différentes** (`/guessyear`, `/guessepisodes`, `/guessgenre`, `/guesscharacter`)",
        _fs("guessyear", "guessepisodes", "guessgenre", "guesscharacter"),
        2,
        "MEDIUM",
        True,
        "Joue à **2** mini-jeux **différents** parmi Guess année / épisodes / genre / perso.",
    ),
]

MISSION_BY_KEY: Dict[str, MissionDef] = {d.key: d for d in MISSION_DEFINITIONS}
MISSION_HINTS: Dict[str, str] = {d.key: d.hint for d in MISSION_DEFINITIONS}

DEFAULT_MISSION_HINT = (
    "Réalise l’objectif décrit ci-dessus ; la progression se met à jour automatiquement."
)


def pick_weighted_random_mission() -> MissionDef:
    """Pondération : EASY ×3, MEDIUM ×2, HARD ×1."""
    import random

    pool: List[MissionDef] = []
    for d in MISSION_DEFINITIONS:
        w = 1 if d.difficulty == "HARD" else 2 if d.difficulty == "MEDIUM" else 3
        pool.extend([d] * w)
    return random.choice(pool)


def mission_state_from_def(d: MissionDef, *, reward_xp: int) -> dict:
    """État JSON stocké dans data/missions.json (sans date / last_reroll)."""
    return {
        "key": d.key,
        "label": d.label,
        "commands": list(d.commands),
        "goal": d.goal,
        "progress": 0,
        "reward_xp": reward_xp,
        "difficulty": d.difficulty,
        "completed": False,
        "distinct": d.distinct,
        "distinct_used": [],
    }
