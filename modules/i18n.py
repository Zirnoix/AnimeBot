# modules/i18n.py — chaînes centralisées (fr / en)
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import discord

_DEFAULT_LANG = "fr"
_LOCALE_DIR = Path(__file__).resolve().parent / "locales"
_CACHE: dict[str, dict[str, Any]] = {}


def _load_locale(lang: str) -> dict[str, Any]:
    if lang in _CACHE:
        return _CACHE[lang]
    path = _LOCALE_DIR / f"{lang}.json"
    if not path.is_file():
        _CACHE[lang] = {}
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _CACHE[lang] = data if isinstance(data, dict) else {}
    except Exception:
        _CACHE[lang] = {}
    return _CACHE[lang]


def reload_locales() -> None:
    """Vide le cache (tests / hot reload)."""
    _CACHE.clear()


def _get_nested(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def value(key: str, lang: str) -> Any:
    """
    Valeur JSON brute (liste, dict, chaîne…) par clé pointée.
    Retombe sur le français si la clé manque.
    """
    lang = lang if lang in ("fr", "en") else _DEFAULT_LANG
    for attempt in (lang, _DEFAULT_LANG):
        try:
            return _get_nested(_load_locale(attempt), key)
        except KeyError:
            continue
    return None


def t(key: str, lang: str, **kwargs: Any) -> str:
    """
    Récupère une chaîne par clé pointée (ex: ``language.set_confirm``).
    Retombe sur le français si la clé manque en anglais.
    """
    lang = lang if lang in ("fr", "en") else _DEFAULT_LANG
    s: str | None = None
    for attempt in (lang, _DEFAULT_LANG):
        try:
            raw = _get_nested(_load_locale(attempt), key)
            if isinstance(raw, str):
                s = raw
                break
        except KeyError:
            continue
    if s is None:
        return key
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s


def _title_from_pairs(n: int, pairs_raw: Any) -> str:
    """pairs_raw: [[req, label], …] trié par req croissant (même logique que core)."""
    if not isinstance(pairs_raw, list) or not pairs_raw:
        return "?"
    pairs: list[tuple[int, str]] = []
    for row in pairs_raw:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            try:
                pairs.append((int(row[0]), str(row[1])))
            except Exception:
                continue
    if not pairs:
        return "?"
    current = pairs[0][1]
    for req, title in pairs:
        if int(n) >= int(req):
            current = title
        else:
            break
    return current


def title_for_global_level(level: int, lang: str) -> str:
    raw = value("xp.titles_global", lang)
    return _title_from_pairs(int(level), raw)


def title_for_quiz_score(score: int, lang: str) -> str:
    raw = value("xp.titles_quiz", lang)
    return _title_from_pairs(int(score), raw)


def weekday_name(lang: str, weekday: int) -> str:
    """weekday: 0=lundi … 6=dimanche (datetime.weekday)."""
    arr = value("common.weekdays", lang)
    wd = int(weekday) % 7
    if isinstance(arr, list) and 0 <= wd < len(arr):
        return str(arr[wd])
    fb = value("common.weekdays", _DEFAULT_LANG)
    if isinstance(fb, list) and 0 <= wd < len(fb):
        return str(fb[wd])
    return "—"


def guild_lang(guild: discord.Guild | None) -> str:
    """Langue pour un salon de guilde ; hors serveur → français."""
    if guild is None:
        return _DEFAULT_LANG
    from modules import locale_store

    return locale_store.get_guild_lang(guild.id)


def interaction_lang(interaction: discord.Interaction) -> str:
    return guild_lang(interaction.guild)


def ctx_lang(ctx: Any) -> str:
    """Langue pour une commande hybride / préfixe."""
    return guild_lang(getattr(ctx, "guild", None))
