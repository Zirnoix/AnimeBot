"""
Stockage et logique métier des signalements de bugs (/reportbug).
Persistance JSON (FileConfig.BUG_REPORTS), cohérent avec le reste du bot.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from modules import core

LOG = logging.getLogger(__name__)

# Gravité → XP de base (validation owner uniquement)
SEVERITY_XP = {"petit": 300, "moyen": 600, "gros": 1000}
HARD_BONUS_XP = 300
REPORT_TYPES = {"bug", "translation"}

# Contenu minimal (évite texte vide / spam)
MIN_TOTAL_CHARS = 120
MIN_FIELD_CHARS = 12

_DEFAULT_STORE: dict[str, Any] = {
    "version": 1,
    "next_id": 1,
    "reports": [],
    "blacklist": [],
    "user_limits": {},
}


def _path() -> str:
    return core.FileConfig.BUG_REPORTS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def paris_today_str() -> str:
    """Jour civil (Europe/Paris) pour le quota « 1 report / jour » et reset minuit."""
    return datetime.now(core.TIMEZONE).strftime("%Y-%m-%d")


def load_store() -> dict[str, Any]:
    raw = core.load_json(_path(), None)
    if not isinstance(raw, dict):
        return dict(_DEFAULT_STORE)
    out = dict(_DEFAULT_STORE)
    out.update(raw)
    if not isinstance(out.get("reports"), list):
        out["reports"] = []
    if not isinstance(out.get("blacklist"), list):
        out["blacklist"] = []
    if not isinstance(out.get("user_limits"), dict):
        out["user_limits"] = {}
    try:
        out["next_id"] = max(1, int(out.get("next_id") or 1))
    except (TypeError, ValueError):
        out["next_id"] = 1
    return out


def save_store(data: dict[str, Any]) -> None:
    core.save_json(_path(), data)


def is_blacklisted(user_id: int) -> bool:
    uid = str(int(user_id))
    with core.DATA_JSON_LOCK:
        st = load_store()
        return uid in set(str(x) for x in st.get("blacklist") or [])


def blacklist_add(user_id: int) -> bool:
    uid = str(int(user_id))
    with core.DATA_JSON_LOCK:
        st = load_store()
        bl = st.setdefault("blacklist", [])
        if uid in bl:
            return False
        bl.append(uid)
        save_store(st)
    return True


def blacklist_remove(user_id: int) -> bool:
    uid = str(int(user_id))
    with core.DATA_JSON_LOCK:
        st = load_store()
        bl = [str(x) for x in st.get("blacklist") or []]
        if uid not in bl:
            return False
        st["blacklist"] = [x for x in bl if x != uid]
        save_store(st)
    return True


def get_blacklist() -> list[str]:
    with core.DATA_JSON_LOCK:
        st = load_store()
        return [str(x) for x in st.get("blacklist") or []]


def _user_lim(st: dict[str, Any], uid: str) -> dict[str, Any]:
    ul = st.setdefault("user_limits", {})
    cur = ul.get(uid)
    if not isinstance(cur, dict):
        cur = {}
        ul[uid] = cur
    return cur


def _can_user_submit_bug_unlocked(st: dict[str, Any], user_id: int) -> Tuple[bool, str]:
    uid = str(int(user_id))
    now = time.time()
    today = paris_today_str()
    if uid in set(str(x) for x in st.get("blacklist") or []):
        return False, "blacklist"
    lim = _user_lim(st, uid)
    try:
        ru = float(lim.get("reject_until_ts") or 0)
    except (TypeError, ValueError):
        ru = 0.0
    if ru > now:
        return False, "reject_cooldown"
    if str(lim.get("last_submitted_day") or "") == today:
        return False, "daily_limit"
    return True, "ok"


def can_user_submit_bug(user_id: int) -> Tuple[bool, str]:
    """
    Retourne (ok, code_message).
    Codes : ok, blacklist, reject_cooldown, daily_limit
    """
    with core.DATA_JSON_LOCK:
        st = load_store()
        return _can_user_submit_bug_unlocked(st, user_id)


def validate_bug_text_parts(
    commande: str,
    probleme: str,
    attendu: str,
    reproduire: str,
) -> Tuple[bool, str]:
    """
    Règles : total ≥ MIN_TOTAL_CHARS ; commande non vide (peut être courte, ex. `/quiz`) ;
    problème, attendu et reproduire ≥ MIN_FIELD_CHARS chacun.
    """
    c = (commande or "").strip()
    p = (probleme or "").strip()
    a = (attendu or "").strip()
    r = (reproduire or "").strip()
    if not c:
        return False, "command_empty"
    total = len(c) + len(p) + len(a) + len(r)
    if total < MIN_TOTAL_CHARS:
        return False, "too_short"
    if len(p) < MIN_FIELD_CHARS or len(a) < MIN_FIELD_CHARS or len(r) < MIN_FIELD_CHARS:
        return False, "field_too_short"
    return True, "ok"


def format_bug_body(
    commande: str,
    probleme: str,
    attendu: str,
    reproduire: str,
) -> str:
    return (
        "**Commande ou système concerné**\n"
        + (commande or "").strip()
        + "\n\n**Problème observé**\n"
        + (probleme or "").strip()
        + "\n\n**Comportement attendu**\n"
        + (attendu or "").strip()
        + "\n\n**Étapes pour reproduire**\n"
        + ((reproduire or "").strip() or "_(non précisé)_")
    )


def create_pending_report(user_id: int, username: str, content: str) -> Optional[int]:
    """
    Réserve le quota journalier et crée un report « pending ».
    Retourne l’id ou None si impossible.
    """
    uid = str(int(user_id))
    today = paris_today_str()
    with core.DATA_JSON_LOCK:
        st = load_store()
        ok, code = _can_user_submit_bug_unlocked(st, user_id)
        if not ok:
            LOG.debug("create_pending_report blocked: %s", code)
            return None
        rid = int(st["next_id"])
        st["next_id"] = rid + 1
        rep = {
            "id": rid,
            "user_id": uid,
            "username": (username or "")[:80],
            "content": content[:8000],
            "created_at": _now_iso(),
            "status": "pending",
            "processed_at": None,
            "treatment": None,
            "report_type": None,
            "severity": None,
            "hard_to_find": None,
            "xp_awarded": 0,
            "reject_cooldown_until_ts": None,
        }
        st.setdefault("reports", []).append(rep)
        lim = _user_lim(st, uid)
        lim["last_submitted_day"] = today
        save_store(st)
    return rid


def _paris_day_from_created_iso(created_at: str) -> Optional[str]:
    try:
        ca = created_at or ""
        dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(core.TIMEZONE).strftime("%Y-%m-%d")
    except Exception:
        return None


def rollback_report(user_id: int, report_id: int) -> None:
    """Annule un report et le quota du jour si l’envoi owner échoue."""
    uid = str(int(user_id))
    rid = int(report_id)
    today_paris = paris_today_str()
    with core.DATA_JSON_LOCK:
        st = load_store()
        reps = st.get("reports") or []
        st["reports"] = [r for r in reps if int(r.get("id") or 0) != rid]
        lim = _user_lim(st, uid)
        has_today = False
        for r in st["reports"]:
            if str(r.get("user_id")) != uid:
                continue
            d = _paris_day_from_created_iso(str(r.get("created_at") or ""))
            if d == today_paris:
                has_today = True
                break
        if not has_today:
            lim["last_submitted_day"] = None
        else:
            lim["last_submitted_day"] = today_paris
        save_store(st)


def get_report(report_id: int) -> Optional[dict[str, Any]]:
    rid = int(report_id)
    with core.DATA_JSON_LOCK:
        st = load_store()
        for r in st.get("reports") or []:
            if int(r.get("id") or 0) == rid:
                return dict(r)
    return None


def count_confirmed_reports_for_user(user_id: int) -> int:
    """Nombre de signalements validés (confirmés) par le propriétaire — affichage /mycard, etc."""
    uid = str(int(user_id))
    n = 0
    with core.DATA_JSON_LOCK:
        st = load_store()
        for r in st.get("reports") or []:
            if str(r.get("user_id")) != uid:
                continue
            if str(r.get("status")) == "confirmed":
                n += 1
    return n


def refuse_report(report_id: int, _owner_id: int) -> Tuple[bool, Optional[dict[str, Any]]]:
    """Refus : 7 jours de blocage pour l’utilisateur."""
    rid = int(report_id)
    with core.DATA_JSON_LOCK:
        st = load_store()
        for r in st.get("reports") or []:
            if int(r.get("id") or 0) != rid:
                continue
            if str(r.get("status")) != "pending":
                return False, None
            uid = str(r.get("user_id") or "")
            r["status"] = "refused"
            r["processed_at"] = _now_iso()
            r["treatment"] = "refused"
            r["xp_awarded"] = 0
            cooldown_end = time.time() + 7 * 86400
            r["reject_cooldown_until_ts"] = cooldown_end
            lim = _user_lim(st, uid)
            lim["reject_until_ts"] = cooldown_end
            save_store(st)
            return True, dict(r)
        return False, None


def dismiss_report_no_sanction(report_id: int, _owner_id: int) -> Tuple[bool, Optional[dict[str, Any]]]:
    """
    Clôture sans sanction : le signalement a été analysé mais ce n’était pas un « vrai » bug
    (déjà réglé, API, redémarrage, cas extrême, etc.). Pas de cooldown 7 jours.
    """
    rid = int(report_id)
    with core.DATA_JSON_LOCK:
        st = load_store()
        for r in st.get("reports") or []:
            if int(r.get("id") or 0) != rid:
                continue
            if str(r.get("status")) != "pending":
                return False, None
            r["status"] = "dismissed"
            r["processed_at"] = _now_iso()
            r["treatment"] = "dismissed_no_sanction"
            r["xp_awarded"] = 0
            r["reject_cooldown_until_ts"] = None
            save_store(st)
            return True, dict(r)
        return False, None


def confirm_report(
    report_id: int,
    _owner_id: int,
    severity: str,
    hard_to_find: bool,
    report_type: str = "bug",
) -> Tuple[bool, Optional[dict[str, Any]], int]:
    """
    Confirme et calcule l’XP. Retourne (ok, report_dict, xp_total).
    """
    rid = int(report_id)
    sev = (severity or "").lower().strip()
    if sev not in SEVERITY_XP:
        return False, None, 0
    rtype = (report_type or "bug").strip().lower()
    if rtype not in REPORT_TYPES:
        rtype = "bug"
    base = SEVERITY_XP[sev]
    bonus = HARD_BONUS_XP if hard_to_find else 0
    total_xp = base + bonus
    with core.DATA_JSON_LOCK:
        st = load_store()
        for r in st.get("reports") or []:
            if int(r.get("id") or 0) != rid:
                continue
            if str(r.get("status")) != "pending":
                return False, None, 0
            r["status"] = "confirmed"
            r["processed_at"] = _now_iso()
            r["treatment"] = "confirmed_translation" if rtype == "translation" else "confirmed"
            r["report_type"] = rtype
            r["severity"] = sev
            r["hard_to_find"] = bool(hard_to_find)
            r["xp_awarded"] = int(total_xp)
            r["reject_cooldown_until_ts"] = None
            save_store(st)
            return True, dict(r), int(total_xp)
        return False, None, 0


def list_reports_summary(limit: int = 20) -> list[dict[str, Any]]:
    with core.DATA_JSON_LOCK:
        st = load_store()
        reps = list(st.get("reports") or [])
    reps.sort(key=lambda x: int(x.get("id") or 0), reverse=True)
    return reps[: max(1, min(limit, 100))]
