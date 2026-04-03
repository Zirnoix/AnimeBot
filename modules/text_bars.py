# modules/text_bars.py — barres de progression texte pour embeds (un seul calcul, plusieurs styles)
from __future__ import annotations

# Style par défaut : badges, stats AniList, missions, XP (cohérent avec la doc utilisateur)
FILLED_PAR = "▰"
EMPTY_PAR = "▱"

# Style « blocs » : timer Guess OP, PV boss (lisible sur fond sombre)
FILLED_BLOCK = "█"
EMPTY_BLOCK = "░"


def pct_bar(
    current: int,
    total: int,
    width: int = 12,
    *,
    filled: str = FILLED_PAR,
    empty: str = EMPTY_PAR,
) -> str:
    """
    Barre proportionnelle : `current` / `total` sur `width` caractères.

    - ``total <= 0`` : toute la largeur en ``empty`` (pas de division).
    - ``current`` est borné à ``[0, total]`` après normalisation de ``total`` à ``>= 1``.
    """
    if width <= 0:
        return ""
    if total <= 0:
        return empty * width
    tot = max(1, int(total))
    cur = max(0, min(int(current or 0), tot))
    n = int(round(width * cur / tot))
    return filled * n + empty * (width - n)


def pct_bar_parallelogram(current: int, total: int, width: int = 12) -> str:
    """▰ rempli, ▱ reste — profil, trophées, stats, missions, ``get_xp_bar``."""
    return pct_bar(current, total, width, filled=FILLED_PAR, empty=EMPTY_PAR)


def pct_bar_blocks(current: int, total: int, width: int = 18) -> str:
    """█ rempli, ░ reste — timers, barres de PV, etc."""
    return pct_bar(current, total, width, filled=FILLED_BLOCK, empty=EMPTY_BLOCK)
