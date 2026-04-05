# modules/i18n.py — chaînes centralisées (fr / en)
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import discord

_LOG = logging.getLogger(__name__)

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


def t_exact(key: str, lang: str, **kwargs: Any) -> str | None:
    """
    Chaîne pour `lang` uniquement (pas de repli sur l’autre langue).
    Utile pour les traductions slash (en-US) : None si la clé manque en anglais.
    """
    lang = lang if lang in ("fr", "en") else _DEFAULT_LANG
    try:
        raw = _get_nested(_load_locale(lang), key)
        if not isinstance(raw, str):
            return None
        if kwargs:
            try:
                return raw.format(**kwargs)
            except Exception:
                return raw
        return raw
    except KeyError:
        return None


def t(key: str, lang: str, **kwargs: Any) -> str:
    """
    Récupère une chaîne par clé pointée (ex: ``language.set_confirm``).
    Retombe sur le français si la clé manque en anglais.
    """
    lang = lang if lang in ("fr", "en") else _DEFAULT_LANG
    s: str | None = None
    resolved_from: str | None = None
    for attempt in (lang, _DEFAULT_LANG):
        try:
            raw = _get_nested(_load_locale(attempt), key)
            if isinstance(raw, str):
                s = raw
                resolved_from = attempt
                break
        except KeyError:
            continue
    if s is None:
        _LOG.debug("i18n missing key %r (not in fr or en)", key)
        return key
    if resolved_from is not None and resolved_from != lang:
        _LOG.debug("i18n key %r missing for lang %s; using %s", key, lang, resolved_from)
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
    """Langue pour un salon de guilde ; hors serveur → français (voir aussi ``interaction_lang`` / ``user_dm_lang``)."""
    if guild is None:
        return _DEFAULT_LANG
    from modules import locale_store

    return locale_store.get_guild_lang(guild.id)


def lang_from_discord_locale(locale: Any) -> str:
    """
    Mappe la locale client Discord (interaction.locale) vers ``fr`` ou ``en``.
    Locales non gérées → ``fr`` (seules ``fr`` et ``en`` existent dans les JSON).
    """
    if locale is None:
        return _DEFAULT_LANG
    val = getattr(locale, "value", None)
    if not isinstance(val, str):
        val = str(locale)
    if val.startswith("en"):
        return "en"
    if val.startswith("fr"):
        return "fr"
    return _DEFAULT_LANG


def user_dm_lang(user_id: int) -> str:
    """
    Langue pour les **MP sans interaction** (récap, alertes tracker, etc.).

    Source : ``client_lang``, mise à jour automatiquement à chaque interaction Discord
    (langue du **client** de l’utilisateur, comme pour les descriptions slash).

    Repli : ancien ``digest_lang`` si présent ; sinon ``fr`` (jamais vu le bot ou locale inconnue).
    """
    try:
        from modules import core

        st = core.load_user_settings() or {}
    except Exception:
        st = {}
    u = st.get(str(int(user_id)), {}) or {}
    for key in ("client_lang", "digest_lang"):
        raw = u.get(key)
        if raw in ("fr", "en"):
            return raw
    return _DEFAULT_LANG


def persist_user_locale_from_interaction(interaction: discord.Interaction) -> None:
    """
    Mémorise ``fr`` / ``en`` selon ``interaction.locale`` pour les prochains MP automatiques.
    Appeler sur (presque) toute interaction utilisateur.
    """
    try:
        user = interaction.user
        if user is None or getattr(user, "bot", False):
            return
        loc = getattr(interaction, "locale", None)
        if loc is None:
            return
        lang = lang_from_discord_locale(loc)
        uid = str(int(user.id))
        from modules import core

        with core.DATA_JSON_LOCK:
            data = dict(core.load_user_settings() or {})
            u = dict(data.get(uid, {}) or {})
            u["client_lang"] = lang
            data[uid] = u
            core.save_user_settings(data)
    except Exception:
        _LOG.debug("persist_user_locale_from_interaction failed", exc_info=True)


def interaction_lang(interaction: discord.Interaction) -> str:
    """En serveur : langue du serveur. En MP : langue du **client Discord** de l’utilisateur (interaction.locale)."""
    if interaction.guild is not None:
        return guild_lang(interaction.guild)
    return lang_from_discord_locale(getattr(interaction, "locale", None))


def ctx_lang(ctx: Any) -> str:
    """En serveur : langue du serveur. En MP avec slash : locale Discord ; sinon ``fr``."""
    g = getattr(ctx, "guild", None)
    if g is not None:
        return guild_lang(g)
    itx = getattr(ctx, "interaction", None)
    if itx is not None:
        return lang_from_discord_locale(getattr(itx, "locale", None))
    return _DEFAULT_LANG
