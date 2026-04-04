# modules/app_cmd_locale.py — descriptions slash : FR par défaut, en-US via CommandTree.set_translator
from __future__ import annotations

from typing import Any, Optional

from discord import Locale, app_commands
from discord.app_commands.translator import Translator, TranslationContextTypes

from modules import i18n

_EN_LOCALES = frozenset({Locale.american_english, Locale.british_english})


def ui_str(i18n_key: str, **kwargs: Any) -> app_commands.locale_str:
    """Texte FR pour l’API ; clé i18n pour remplir en-US au sync."""
    text = i18n.t(i18n_key, "fr", **kwargs)
    if kwargs:
        return app_commands.locale_str(text, i18n_key=i18n_key, i18n_fmt=kwargs)
    return app_commands.locale_str(text, i18n_key=i18n_key)


def _help_ac_slug(value: str) -> str:
    """Clé stable pour slash.help_ac.<slug> (optionnel en JSON)."""
    raw = (value or "").strip().lower().replace(" ", "_")
    out = []
    for c in raw:
        out.append(c if c.isalnum() or c == "_" else "_")
    s = "".join(out).strip("_")
    return s[:96] if s else "x"


def help_ac_choice(disp: str, value: str) -> app_commands.locale_str:
    """Autocomplete /help : libellé FR par défaut ; EN via slash.help_ac.<slug> ou repli sur le libellé."""
    return app_commands.locale_str(
        disp[:100],
        i18n_key="slash.help_ac",
        help_ac_slug=_help_ac_slug(value),
    )


class AppCommandTranslator(Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: Locale,
        context: TranslationContextTypes,
    ) -> Optional[str]:
        if locale not in _EN_LOCALES:
            return None
        key = string.extras.get("i18n_key")
        if not key or not isinstance(key, str):
            return None
        if key == "slash.help_ac":
            slug = string.extras.get("help_ac_slug")
            if isinstance(slug, str) and slug:
                sub = i18n.t_exact(f"slash.help_ac.{slug}", "en")
                if sub is not None:
                    return sub
            return string.message
        fmt = string.extras.get("i18n_fmt")
        if isinstance(fmt, dict) and fmt:
            return i18n.t_exact(key, "en", **fmt)
        return i18n.t_exact(key, "en")
