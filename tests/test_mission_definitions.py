"""Tests sur les définitions de missions (sans Discord)."""
from __future__ import annotations

from modules.mission_definitions import (
    MISSION_BY_KEY,
    mission_state_from_def,
    pick_weighted_random_mission,
)


def test_mission_state_from_def_shape() -> None:
    d = MISSION_BY_KEY["use_next"]
    st = mission_state_from_def(d, reward_xp=42)
    assert st["key"] == "use_next"
    assert st["goal"] == d.goal
    assert st["reward_xp"] == 42
    assert st["progress"] == 0
    assert st["completed"] is False
    assert st["distinct_used"] == []


def test_pick_weighted_random_mission_returns_defined() -> None:
    for _ in range(20):
        m = pick_weighted_random_mission()
        assert m.key in MISSION_BY_KEY
