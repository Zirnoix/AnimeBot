"""Tests unitaires (sans Discord) pour la logique titres / normalisation."""
from __future__ import annotations

from cogs.quiz import TitleMatcher
from modules import core


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
