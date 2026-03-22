"""Tests unitaires (sans Discord) pour la logique titres / normalisation."""
from __future__ import annotations

import os
import sys

# Racine du projet
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("DISCORD_BOT_TOKEN", "0" * 50)

from cogs.quiz import TitleMatcher  # noqa: E402
from modules import core  # noqa: E402


def test_emoji_only_does_not_match_any_title() -> None:
    m = TitleMatcher()
    titles = {"Naruto", "One Piece"}
    assert m.find_matches("😀😀", titles) == []
    assert m.find_matches("", titles) == []
    assert m.find_matches("   ", titles) == []


def test_real_guess_still_matches() -> None:
    m = TitleMatcher()
    assert m.find_matches("naruto", {"Naruto"})


def test_find_similar_titles_empty_query() -> None:
    assert core.find_similar_titles("") == []
    assert core.find_similar_titles("   ") == []


def test_normalize_strips_emoji_to_empty() -> None:
    assert core.normalize("🔥🔥") == ""
