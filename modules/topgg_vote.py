# modules/topgg_vote.py
"""Persistance votes Top.gg + helpers (webhook, cooldown, rappels MP)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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
    return max(0, int(os.getenv("TOPGG_VOTE_XP", "65")))


def _bot_tz() -> ZoneInfo:
    name = (os.getenv("BOT_TIMEZONE") or "Europe/Paris").strip() or "Europe/Paris"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Paris")


def _calendar_date(ts: int) -> date:
    return datetime.fromtimestamp(int(ts), tz=_bot_tz()).date()


def streak_bonus_xp(streak_days: int) -> int:
    """XP bonus selon la série de jours consécutifs (au moins un vote / jour)."""
    per = max(0, int(os.getenv("TOPGG_STREAK_BONUS_PER_DAY", "4")))
    cap = max(0, int(os.getenv("TOPGG_STREAK_BONUS_CAP", "40")))
    return min(cap, max(0, int(streak_days)) * per)


def loyalty_bonus_xp(total_votes: int) -> int:
    """XP bonus selon le nombre total de votes (fidélité)."""
    every = max(1, int(os.getenv("TOPGG_LOYALTY_EVERY_VOTES", "10")))
    cap = max(0, int(os.getenv("TOPGG_LOYALTY_BONUS_CAP", "30")))
    per = max(0, int(os.getenv("TOPGG_LOYALTY_PER_BONUS", "2")))
    return min(cap, (max(0, int(total_votes)) // every) * per)


@dataclass(frozen=True)
class VoteReward:
    total_votes: int
    streak: int
    best_streak: int
    base_xp: int
    streak_bonus: int
    loyalty_bonus: int
    subtotal_xp: int

    def total_after_weekend(self, is_weekend: bool, mult: float) -> int:
        if not is_weekend:
            return max(0, self.subtotal_xp)
        return max(0, int(self.subtotal_xp * mult))


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
    u.setdefault("vote_count", 0)
    u.setdefault("vote_streak", 0)
    u.setdefault("best_streak", 0)
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


def get_vote_stats(uid: int) -> dict[str, int]:
    data = load_vote_data()
    u = _ensure_user(data, uid)
    return {
        "vote_count": int(u.get("vote_count") or 0),
        "streak": int(u.get("vote_streak") or 0),
        "best_streak": int(u.get("best_streak") or 0),
    }


def record_successful_vote(uid: int) -> VoteReward:
    """Après un upvote Top.gg : met à jour série / totaux et calcule l’XP (avant bonus week-end)."""
    data = load_vote_data()
    now = int(time.time())
    u = _ensure_user(data, uid)
    prev_ts = int(u.get("last_vote_ts") or 0)
    old_streak = int(u.get("vote_streak") or 0)

    vote_count = int(u.get("vote_count") or 0) + 1
    today = _calendar_date(now)

    if prev_ts <= 0:
        new_streak = 1
    else:
        prev_date = _calendar_date(prev_ts)
        if today == prev_date:
            new_streak = max(1, old_streak)
        elif today == prev_date + timedelta(days=1):
            new_streak = old_streak + 1
        else:
            new_streak = 1

    best_streak = max(int(u.get("best_streak") or 0), new_streak)

    u["last_vote_ts"] = now
    u["vote_count"] = vote_count
    u["vote_streak"] = new_streak
    u["best_streak"] = best_streak
    u["reminder_sent_for_eligible"] = None

    base = vote_xp_amount()
    sb = streak_bonus_xp(new_streak)
    lb = loyalty_bonus_xp(vote_count)
    subtotal = base + sb + lb

    save_vote_data(data)

    return VoteReward(
        total_votes=vote_count,
        streak=new_streak,
        best_streak=best_streak,
        base_xp=base,
        streak_bonus=sb,
        loyalty_bonus=lb,
        subtotal_xp=subtotal,
    )


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
