"""
Compteurs pour les trophées (hors Discord) — utilisé par profile / mybadges.
"""
from __future__ import annotations

from typing import Any, Dict


def badge_count_for_spec(spec: dict, counts: Dict[str, Any]) -> int:
    source = spec.get("source", "")
    if source.startswith("mini_sum:"):
        keys = source.split(":", 1)[1].split(",")
        return sum(int(counts.get(k.strip(), 0)) for k in keys)
    if source.startswith("mini:"):
        key = source.split(":", 1)[1]
        return int(counts.get(key, 0))
    if source.startswith("streak:"):
        key = source.split(":", 1)[1]
        return int(counts.get(f"streak_{key}", counts.get("streak_days", 0)))
    if source.startswith("anilist:"):
        key = source.split(":", 1)[1]
        return int(counts.get(f"anilist_{key}", 0))
    if source.startswith("time:"):
        key = source.split(":", 1)[1]
        return int(counts.get(f"time_{key}", 0))
    if source.startswith("command:"):
        key = source.split(":", 1)[1]
        return int(counts.get(f"command_{key}", 0))
    return 0
