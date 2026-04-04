# cogs/reminder_digest.py
from __future__ import annotations

import logging
from typing import Any

import discord
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View

from modules import core
from modules import i18n
from modules.app_cmd_locale import ui_str

LOG = logging.getLogger(__name__)
COLOR_OK = discord.Color.blurple()


def _load_settings() -> dict:
    return core.load_user_settings() or {}


def _save_settings(data: dict) -> None:
    core.save_user_settings(data or {})


def _get_user_pref(uid: int) -> dict:
    return _load_settings().get(str(uid), {})


def _set_user_pref(uid: int, **updates: Any) -> None:
    data = _load_settings()
    u = data.get(str(uid), {})
    u.update(updates)
    data[str(uid)] = u
    _save_settings(data)


def _hhmm_valid(s: str) -> bool:
    try:
        hh, mm = (s or "").strip().split(":")
        h = int(hh)
        m = int(mm)
        return 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return False


def _normalize_hhmm(s: str) -> str | None:
    """Retourne HH:MM normalisé ou None si invalide."""
    if not _hhmm_valid(s):
        return None
    hh, mm = (s or "").strip().split(":")
    return f"{int(hh):02d}:{int(mm):02d}"


def _modal_default_hhmm(s: str) -> str:
    """Valeur par défaut du champ heure (modal)."""
    return _normalize_hhmm(s) or "08:00"


def _daily_summary_effective(uid: int, pref: dict) -> bool:
    """Aligné sur bot.send_daily_summaries (legacy preferences.json)."""
    daily = pref.get("daily_summary")
    if daily is not None:
        return bool(daily)
    prefs_all = core.load_preferences() or {}
    if str(uid) in prefs_all:
        return True
    return True


def _recap_embed_for_user(uid: int, lang: str) -> discord.Embed:
    """Embed du panneau /recap (état courant)."""
    pref = _get_user_pref(uid)
    on = _daily_summary_effective(uid, pref)
    hh = pref.get("alert_time") or core.get_config().get("default_alert_time", "08:00")
    linked = core.get_linked_username(uid)
    link_txt = f"**{linked}**" if linked else i18n.t("recap.link_none", lang)
    state = i18n.t("recap.state_on", lang) if on else i18n.t("recap.state_off", lang)
    em = discord.Embed(
        title=i18n.t("recap.embed_title", lang),
        description=i18n.t(
            "recap.embed_desc",
            lang,
            link_txt=link_txt,
            state=state,
            hh=hh,
        ),
        color=COLOR_OK,
    )
    em.set_footer(text=i18n.t("recap.embed_footer", lang))
    return em


class RecapTimeModal(Modal):
    """Saisie HH:MM (fuseau du bot) — plus lisible qu’un long menu déroulant."""

    def __init__(self, user_id: int, default_hhmm: str, lang: str) -> None:
        super().__init__(title=i18n.t("recap.modal_title", lang)[:45])
        self.user_id = user_id
        self.lang = lang
        self._time = TextInput(
            label=i18n.t("recap.modal_label_time", lang)[:45],
            default=(default_hhmm or "08:00")[:5],
            placeholder=i18n.t("recap.modal_ph_time", lang)[:100],
            min_length=4,
            max_length=5,
            required=True,
        )
        self.add_item(self._time)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lg = self.lang
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(i18n.t("recap.err_not_yours_form", lg), ephemeral=True)
            return
        norm = _normalize_hhmm(self._time.value)
        if not norm:
            await interaction.response.send_message(
                i18n.t("recap.err_invalid_time", lg),
                ephemeral=True,
            )
            return
        _set_user_pref(interaction.user.id, daily_summary=True, alert_time=norm)
        em = _recap_embed_for_user(interaction.user.id, lg)
        view = _recap_view_for_user(interaction.user.id, lg)
        await interaction.response.edit_message(embed=em, view=view, content=None)


class RecapSetupView(View):
    """Boutons + modal de saisie : activer / désactiver / régler l’heure au clavier."""

    def __init__(self, user_id: int, default_hhmm: str, lang: str) -> None:
        super().__init__(timeout=300)
        self.user_id = user_id
        self.default_hhmm = default_hhmm
        self.lang = lang
        self.add_item(RecapEnableButton(user_id, lang))
        self.add_item(RecapDisableButton(user_id, lang))
        self.add_item(RecapTimeModalButton(user_id, default_hhmm, lang))
        self.add_item(RecapCloseButton(user_id, lang))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                i18n.t("recap.err_not_yours", self.lang), ephemeral=True,
            )
            return False
        return True


class RecapEnableButton(Button):
    def __init__(self, user_id: int, lang: str) -> None:
        super().__init__(
            label=i18n.t("recap.btn_enable", lang)[:80],
            style=discord.ButtonStyle.success,
            row=0,
        )
        self.user_id = user_id
        self.lang = lang

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(i18n.t("recap.err_not_yours", self.lang), ephemeral=True)
            return
        _set_user_pref(interaction.user.id, daily_summary=True)
        em = _recap_embed_for_user(interaction.user.id, self.lang)
        view = _recap_view_for_user(interaction.user.id, self.lang)
        await interaction.response.edit_message(embed=em, view=view, content=None)


class RecapDisableButton(Button):
    def __init__(self, user_id: int, lang: str) -> None:
        super().__init__(
            label=i18n.t("recap.btn_disable", lang)[:80],
            style=discord.ButtonStyle.danger,
            row=0,
        )
        self.user_id = user_id
        self.lang = lang

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(i18n.t("recap.err_not_yours", self.lang), ephemeral=True)
            return
        _set_user_pref(interaction.user.id, daily_summary=False)
        await interaction.response.edit_message(
            content=i18n.t("recap.disabled_msg", self.lang),
            embed=None,
            view=None,
        )


class RecapTimeModalButton(Button):
    def __init__(self, user_id: int, default_hhmm: str, lang: str) -> None:
        super().__init__(
            label=i18n.t("recap.btn_time", lang)[:80],
            style=discord.ButtonStyle.primary,
            row=0,
        )
        self.user_id = user_id
        self.default_hhmm = default_hhmm
        self.lang = lang

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(i18n.t("recap.err_not_yours", self.lang), ephemeral=True)
            return
        await interaction.response.send_modal(RecapTimeModal(self.user_id, self.default_hhmm, self.lang))


class RecapCloseButton(Button):
    def __init__(self, user_id: int, lang: str) -> None:
        super().__init__(
            label=i18n.t("recap.btn_close", lang)[:80],
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.user_id = user_id
        self.lang = lang

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(i18n.t("recap.err_not_yours", self.lang), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=i18n.t("recap.closed_msg", self.lang),
            embed=None,
            view=None,
        )


def _recap_view_for_user(uid: int, lang: str) -> RecapSetupView:
    pref = _get_user_pref(uid)
    hh = pref.get("alert_time") or core.get_config().get("default_alert_time", "08:00")
    return RecapSetupView(uid, _modal_default_hhmm(hh), lang)


class ReminderDigest(commands.Cog):
    """Récap MP « sorties du jour » + /setalert."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="recap",
        description=ui_str("slash.recap"),
    )
    async def recap(self, ctx: commands.Context) -> None:
        """Slash : defer puis followup explicite (évite « réfléchit » infini si followup mal résolu)."""
        lg = i18n.ctx_lang(ctx)
        try:
            if ctx.interaction is not None:
                await ctx.defer(ephemeral=True)

            em = _recap_embed_for_user(ctx.author.id, lg)
            view = _recap_view_for_user(ctx.author.id, lg)

            if ctx.interaction is not None:
                await ctx.interaction.followup.send(embed=em, view=view, ephemeral=True)
            else:
                await ctx.reply(embed=em, view=view, delete_after=180)
        except Exception as e:
            LOG.exception("recap: %s", e)
            detail = f"{type(e).__name__}: {e}"
            err = i18n.t("recap.err_generic", lg, detail=detail)
            try:
                if ctx.interaction is not None:
                    if ctx.interaction.response.is_done():
                        await ctx.interaction.followup.send(err, ephemeral=True)
                    else:
                        await ctx.interaction.response.send_message(err, ephemeral=True)
                else:
                    await ctx.reply(err)
            except Exception:
                LOG.exception("recap: échec envoi message d’erreur")

    @commands.hybrid_command(
        name="setalert",
        description=ui_str("slash.setalert"),
    )
    async def setalert(self, ctx: commands.Context, heure: str) -> None:
        lg = i18n.ctx_lang(ctx)
        if not _hhmm_valid(heure):
            return await ctx.reply(i18n.t("recap.setalert_bad", lg), ephemeral=True)
        _set_user_pref(ctx.author.id, alert_time=heure)
        await ctx.reply(
            i18n.t("recap.setalert_ok", lg, heure=heure),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReminderDigest(bot))
