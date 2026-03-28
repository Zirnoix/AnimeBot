# cogs/reminder_digest.py
from __future__ import annotations

import logging
from typing import Any

import discord
from discord.ext import commands
from discord.ui import Select, View

from modules import core

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
        hh, mm = s.split(":")
        h = int(hh)
        m = int(mm)
        return 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return False


def _daily_summary_effective(uid: int, pref: dict) -> bool:
    """Aligné sur bot.send_daily_summaries (legacy preferences.json)."""
    daily = pref.get("daily_summary")
    if daily is not None:
        return bool(daily)
    prefs_all = core.load_preferences() or {}
    if str(uid) in prefs_all:
        return True
    return True


class RecapSetupView(View):
    """Menu éphémère : activer / désactiver / choisir une heure courante."""

    def __init__(self, user_id: int) -> None:
        super().__init__(timeout=300)
        self.user_id = user_id
        opts: list[discord.SelectOption] = []
        for label, val in (
            ("✅ Activer le récap (MP)", "on_keep"),
            ("⏹️ Désactiver le récap", "off"),
        ):
            opts.append(discord.SelectOption(label=label[:100], value=val))
        for h in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23):
            hhmm = f"{h:02d}:00"
            opts.append(
                discord.SelectOption(
                    label=f"Activer à {hhmm}",
                    value=f"on_{hhmm}",
                    description="Heure d’envoi (fuseau du bot)",
                )
            )
        self.add_item(RecapActionSelect(opts))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Ce panneau n’est pas pour toi.", ephemeral=True)
            return False
        return True


class RecapActionSelect(Select):
    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="Choisir : activer / désactiver / heure…",
            min_values=1,
            max_values=1,
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        v = self.values[0]
        uid = interaction.user.id
        if v == "off":
            _set_user_pref(uid, daily_summary=False)
            await interaction.response.edit_message(
                content="⏹️ Récap **désactivé**. Tu peux rouvrir **`/recap`** pour le rallumer.",
                embed=None,
                view=None,
            )
            return
        if v == "on_keep":
            _set_user_pref(uid, daily_summary=True)
            pref = _get_user_pref(uid)
            hh = pref.get("alert_time") or core.get_config().get("default_alert_time", "08:00")
            await interaction.response.edit_message(
                content=(
                    f"✅ Récap **activé** — envoi vers **`{hh}`** (fuseau du bot).\n"
                    "Tu peux changer l’heure avec **`/setalert HH:MM`**."
                ),
                embed=None,
                view=None,
            )
            return
        if v.startswith("on_"):
            hhmm = v[3:]
            if _hhmm_valid(hhmm):
                _set_user_pref(uid, daily_summary=True, alert_time=hhmm)
                await interaction.response.edit_message(
                    content=(
                        f"✅ Récap **activé** — envoi vers **`{hhmm}`** (fuseau du bot).\n"
                        "Pour une autre heure : **`/setalert HH:MM`**."
                    ),
                    embed=None,
                    view=None,
                )
                return
        await interaction.response.send_message("❌ Choix invalide.", ephemeral=True)


class ReminderDigest(commands.Cog):
    """Récap MP « sorties du jour » + /setalert (ancien /dailysummary ; /reminder supprimé)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="recap",
        description="Configurer le récap MP des sorties du jour (compte AniList lié). Menu éphémère.",
    )
    async def recap(self, ctx: commands.Context) -> None:
        """Slash : defer puis followup explicite (évite « réfléchit » infini si followup mal résolu)."""
        try:
            if ctx.interaction is not None:
                await ctx.defer(ephemeral=True)

            pref = _get_user_pref(ctx.author.id)
            on = _daily_summary_effective(ctx.author.id, pref)
            hh = pref.get("alert_time") or core.get_config().get("default_alert_time", "08:00")
            linked = core.get_linked_username(ctx.author.id)
            link_txt = f"**{linked}**" if linked else "_(aucun — utilise `/linkanilist`)_"
            em = discord.Embed(
                title="📬 Récap quotidien — « Sorties du jour »",
                description=(
                    "Configure le **même** récap MP que l’embed **« Sorties du … »** (liste à puces, "
                    "pas l’ancien message détaillé supprimé).\n\n"
                    "Un **message privé** chaque jour à l’heure choisie, selon **ton** compte AniList.\n\n"
                    f"• Compte lié : {link_txt}\n"
                    f"• État : **{'activé' if on else 'désactivé'}** · heure : **`{hh}`** (fuseau du bot)\n\n"
                    "Menu ci-dessous : activer / désactiver / heure pleine. "
                    "Pour **08:30** etc. : **`/setalert`**."
                ),
                color=COLOR_OK,
            )
            em.set_footer(text="/setalert HH:MM · /linkanilist")
            view = RecapSetupView(ctx.author.id)

            if ctx.interaction is not None:
                await ctx.interaction.followup.send(embed=em, view=view, ephemeral=True)
            else:
                await ctx.reply(embed=em, view=view, delete_after=180)
        except Exception as e:
            LOG.exception("recap: %s", e)
            try:
                if ctx.interaction is not None:
                    if ctx.interaction.response.is_done():
                        await ctx.interaction.followup.send(
                            f"❌ Erreur `/recap` : `{type(e).__name__}: {e}`",
                            ephemeral=True,
                        )
                    else:
                        await ctx.interaction.response.send_message(
                            f"❌ Erreur `/recap` : `{type(e).__name__}: {e}`",
                            ephemeral=True,
                        )
                else:
                    await ctx.reply(f"❌ Erreur `/recap` : `{type(e).__name__}: {e}`")
            except Exception:
                LOG.exception("recap: échec envoi message d’erreur")

    @commands.hybrid_command(
        name="dailysummary",
        hidden=True,
        description="(Obsolète) Utilise /recap à la place.",
    )
    async def dailysummary_deprecated(self, ctx: commands.Context) -> None:
        await ctx.reply(
            "ℹ️ La commande **`/dailysummary`** a été renommée en **`/recap`**. Utilise **`/recap`** pour le menu.",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="setalert",
        description="Heure (HH:MM) du récap MP « sorties du jour » (/recap), fuseau du bot.",
    )
    async def setalert(self, ctx: commands.Context, heure: str) -> None:
        if not _hhmm_valid(heure):
            return await ctx.reply("❌ Format invalide. Exemple : `08:00`", ephemeral=True)
        _set_user_pref(ctx.author.id, alert_time=heure)
        await ctx.reply(
            f"⏰ Heure réglée sur **{heure}** (fuseau du bot) — utilisée par le récap **`/recap`**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReminderDigest(bot))
