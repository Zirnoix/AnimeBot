# modules/topgg_vote.py
"""Persistance votes Top.gg + helpers (webhook, cooldown, rappels MP)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

LOG = logging.getLogger(__name__)

_DATA_LOCK = threading.RLock()
_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "topgg_vote.json")


def _ensure_parent() -> None:
    os.makedirs(os.path.dirname(_DATA_PATH), exist_ok=True)


def load_vote_data() -> dict[str, Any]:
    with _DATA_LOCK:
        try:
            if os.path.isfile(_DATA_PATH):
                with open(_DATA_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            LOG.warning("topgg_vote: lecture %s: %s", _DATA_PATH, e)
        return {"users": {}}


def save_vote_data(data: dict[str, Any]) -> None:
    with _DATA_LOCK:
        _ensure_parent()
        tmp = _DATA_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
        os.replace(tmp, _DATA_PATH)


def cooldown_seconds() -> int:
    return max(60, int(os.getenv("TOPGG_VOTE_COOLDOWN_SEC", "43200")))


def vote_xp_amount() -> int:
    return max(0, int(os.getenv("TOPGG_VOTE_XP", "45")))


def webhook_secret() -> str:
    return (os.getenv("TOPGG_WEBHOOK_SECRET") or "").strip()


def vote_page_url(bot_user_id: int) -> str:
    custom = (os.getenv("TOPGG_VOTE_URL") or "").strip()
    if custom:
        return custom
    return f"https://top.gg/bot/{int(bot_user_id)}/vote"


def _ensure_user(data: dict[str, Any], uid: int) -> dict[str, Any]:
    u = data.setdefault("users", {}).setdefault(str(int(uid)), {})
    u.setdefault("last_vote_ts", 0)
    u.setdefault("reminder", False)
    u.setdefault("reminder_sent_for_eligible", None)
    return u


def set_reminder(uid: int, enabled: bool) -> None:
    data = load_vote_data()
    u = _ensure_user(data, uid)
    u["reminder"] = bool(enabled)
    save_vote_data(data)


def get_reminder(uid: int) -> bool:
    data = load_vote_data()
    u = _ensure_user(data, uid)
    return bool(u.get("reminder"))


def last_vote_ts(uid: int) -> int:
    data = load_vote_data()
    u = _ensure_user(data, uid)
    return int(u.get("last_vote_ts") or 0)


def next_vote_ts(uid: int) -> int:
    lv = last_vote_ts(uid)
    if lv <= 0:
        return 0
    return lv + cooldown_seconds()


def record_successful_vote(uid: int) -> None:
    """Après un upvote confirmé par Top.gg."""
    data = load_vote_data()
    now = int(time.time())
    u = _ensure_user(data, uid)
    u["last_vote_ts"] = now
    u["reminder_sent_for_eligible"] = None
    save_vote_data(data)


def mark_reminder_sent(uid: int, eligible_ts: int) -> None:
    data = load_vote_data()
    u = _ensure_user(data, uid)
    u["reminder_sent_for_eligible"] = int(eligible_ts)
    save_vote_data(data)


def iter_reminder_candidates(now: int) -> list[tuple[int, int]]:
    """
    Utilisateurs avec rappel activé, ayant déjà voté au moins une fois,
    pour lesquels now >= next_vote et pas encore notifiés pour ce créneau.
    Retourne [(user_id, eligible_ts), ...]
    """
    cd = cooldown_seconds()
    out: list[tuple[int, int]] = []
    data = load_vote_data()
    for suid, u in (data.get("users") or {}).items():
        if not u.get("reminder"):
            continue
        try:
            uid = int(suid)
        except ValueError:
            continue
        lv = int(u.get("last_vote_ts") or 0)
        if lv <= 0:
            continue
        eligible = lv + cd
        if now < eligible:
            continue
        sent = u.get("reminder_sent_for_eligible")
        if sent is not None and int(sent) == eligible:
            continue
        out.append((uid, eligible))
    return out
