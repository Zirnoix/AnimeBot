"""Tests pour badge_count_for_spec (trophées / compteurs)."""
from __future__ import annotations

from modules.badge_helpers import badge_count_for_spec


def test_mini_sum_adds_keys() -> None:
    spec = {"source": "mini_sum:guessyear,guessepisodes"}
    counts = {"guessyear": 2, "guessepisodes": 3}
    assert badge_count_for_spec(spec, counts) == 5


def test_mini_single_key() -> None:
    spec = {"source": "mini:guessyear"}
    assert badge_count_for_spec(spec, {"guessyear": 7}) == 7


def test_streak_prefers_streak_key() -> None:
    spec = {"source": "streak:guess"}
    counts = {"streak_guess": 4, "streak_days": 99}
    assert badge_count_for_spec(spec, counts) == 4


def test_streak_fallback_streak_days() -> None:
    spec = {"source": "streak:missing"}
    counts = {"streak_days": 12}
    assert badge_count_for_spec(spec, counts) == 12


def test_unknown_source_returns_zero() -> None:
    assert badge_count_for_spec({"source": "other:foo"}, {}) == 0
