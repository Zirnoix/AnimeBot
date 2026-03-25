"""
Logique pure de progression des missions (testable sans Discord).
"""
from __future__ import annotations

from typing import Any, Dict


def mission_is_distinct(m: Dict[str, Any]) -> bool:
    """True = une même commande / clé ne compte qu’une fois vers l’objectif."""
    if "distinct" in m:
        return bool(m["distinct"])
    return m.get("key") == "use_3_tracking"


def mission_apply_progress(m: Dict[str, Any], cmd: str) -> bool:
    """
    Met à jour m en place. Retourne True si la progression a changé.
    """
    cmd_set = set(m.get("commands", []))
    if cmd not in cmd_set:
        return False
    before = int(m.get("progress", 0))

    if mission_is_distinct(m):
        used = list(m.get("distinct_used", []))
        if cmd in used:
            return False
        used.append(cmd)
        m["distinct_used"] = used
        m["progress"] = len(used)
    else:
        m["progress"] = before + 1

    return int(m.get("progress", 0)) != before
