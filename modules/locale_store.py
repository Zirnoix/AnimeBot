# modules/locale_store.py — langue par serveur (persistant)
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

_PATH = Path("data/guild_locale.json")
_LOCK = Lock()
_ALLOWED = frozenset({"fr", "en"})


def _read() -> dict:
    if not _PATH.exists():
        return {}
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(data: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_guild_lang(guild_id: int) -> str:
    """Langue du serveur : ``fr`` (défaut) ou ``en``."""
    with _LOCK:
        raw = (_read().get(str(int(guild_id))) or "fr")
    return raw if raw in _ALLOWED else "fr"


def set_guild_lang(guild_id: int, lang: str) -> None:
    """Enregistre ``fr`` ou ``en``."""
    lang = (lang or "fr").lower()
    if lang not in _ALLOWED:
        lang = "fr"
    with _LOCK:
        data = _read()
        data[str(int(guild_id))] = lang
        _write(data)
