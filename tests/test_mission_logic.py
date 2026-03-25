"""Tests pour la progression des missions (sans Discord)."""
from __future__ import annotations

from modules.mission_logic import mission_apply_progress


def test_non_distinct_increments_each_valid_command() -> None:
    m = {
        "commands": ["guessyear"],
        "goal": 3,
        "progress": 0,
        "distinct": False,
    }
    assert mission_apply_progress(m, "guessyear") is True
    assert m["progress"] == 1
    assert mission_apply_progress(m, "guessyear") is True
    assert m["progress"] == 2


def test_distinct_counts_command_once() -> None:
    m = {
        "commands": ["a", "b"],
        "goal": 2,
        "progress": 0,
        "distinct": True,
        "distinct_used": [],
    }
    assert mission_apply_progress(m, "a") is True
    assert m["progress"] == 1
    assert mission_apply_progress(m, "a") is False
    assert m["progress"] == 1
    assert mission_apply_progress(m, "b") is True
    assert m["progress"] == 2


def test_wrong_command_no_op() -> None:
    m = {"commands": ["x"], "progress": 0, "distinct": False}
    assert mission_apply_progress(m, "y") is False
    assert m["progress"] == 0


def test_legacy_use_3_tracking_is_distinct() -> None:
    m = {
        "key": "use_3_tracking",
        "commands": ["next"],
        "goal": 3,
        "progress": 0,
        "distinct_used": [],
    }
    assert mission_apply_progress(m, "next") is True
    assert m["progress"] == 1
    assert mission_apply_progress(m, "next") is False
    assert m["progress"] == 1
