"""
Mini-jeux communautaires : raid boss (planning hebdo + alerte admin), chain quiz,
« qui est-ce » (image floutée).

Commandes en slash (le préfixe `!` n’est pas utilisé pour ce cog).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from time import monotonic
from typing import Any, Optional, Set

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, ChannelSelect, Modal, Select, TextInput, View
from PIL import Image, ImageFilter

from modules import abuse
from modules import anilist_gate
from modules import core
from modules import i18n
from modules.app_cmd_locale import ui_str
from modules import higherlower_combine


def _cg(lg: str, key: str, **kwargs: Any) -> str:
    return i18n.t(f"community_games.{key}", lg, **kwargs)
from modules import minigame_lock
from modules.text_bars import pct_bar_blocks
from modules.core import normalize

LOG = logging.getLogger(__name__)


def _raid_guesswho_name_match(guess: str, correct_name: str, qz: Any) -> bool:
    """Accepte prénom/nom dans un ordre ou l’autre (ex. Kageyama Tobio vs Tobio Kageyama)."""
    if qz and getattr(qz, "title_matcher", None):
        if qz.title_matcher.find_matches(guess, {correct_name}):  # type: ignore[attr-defined]
            return True
    if normalize(guess) == normalize(correct_name):
        return True
    tg = tuple(sorted(normalize(guess).split()))
    tc = tuple(sorted(normalize(correct_name).split()))
    return bool(tg) and tg == tc

async def _require_slash(ctx: commands.Context, name: str) -> bool:
    """True si on peut continuer (invocation slash)."""
    if ctx.interaction is None:
        lg = i18n.ctx_lang(ctx)
        await ctx.send(i18n.t("common.slash_only", lg, name=name))
        return False
    return True


def _raid_mode_tier_key(mode: str, lang: str) -> str:
    mt = i18n.value("raid.mode_tier", lang) or i18n.value("raid.mode_tier", "fr") or {}
    if isinstance(mt, dict) and mode in mt:
        return str(mt[mode])
    return "easy"


def _raid_tier_label(mode: str, lang: str) -> str:
    return i18n.t(f"raid.tier.{_raid_mode_tier_key(mode, lang)}", lang)


def _raid_mode_label(mode: str, lang: str) -> str:
    return i18n.t(f"raid.mode.{mode}", lang)


RAID_DATA_PATH = os.path.join("data", "boss_raid.json")
SORT_CHAIN = ("easy", "medium", "hard")
SORT_TO_ANILIST = {
    "easy": "POPULARITY_DESC",
    "medium": "SCORE_DESC",
    "hard": "TRENDING_DESC",
}

# guesswho : division taille, flou gaussien, timeout (s), XP si victoire
GUESSWHO_MODES: dict[str, tuple[int, float, float, int]] = {
    "easy": (5, 4.0, 55.0, 18),
    "medium": (8, 6.0, 45.0, 28),
    "hard": (12, 9.0, 38.0, 42),
}

_active_raids: dict[int, bool] = {}  # guild_id -> running

# Verrou par guilde : évite deux lancements simultanés (confirm admin + scheduler, ou double clic).
_raid_spawn_locks: dict[int, asyncio.Lock] = {}
_raid_spawn_lock_meta = asyncio.Lock()


async def _raid_spawn_lock_for(guild_id: int) -> asyncio.Lock:
    async with _raid_spawn_lock_meta:
        if guild_id not in _raid_spawn_locks:
            _raid_spawn_locks[guild_id] = asyncio.Lock()
        return _raid_spawn_locks[guild_id]


# ---------- Raid boss v2 (inscription + défis perso + journal) ----------
RAID_JOIN_SECONDS = 120.0
RAID_ROUND_SECONDS = 95.0
RAID_MAX_ROUNDS = 12
# PV du boss = nombre d’inscrits × ce coefficient (ex. 2 joueurs → 12 000 HP)
RAID_HP_PER_PLAYER = 6000
# Dégâts par coup selon le mode choisi à l’inscription (min, max) — tirage aléatoire chaque manche
RAID_DAMAGE_BY_MODE: dict[str, tuple[int, int]] = {
    "guesscharacter": (400, 720),
    "guessyear": (520, 880),
    "guessepisodes": (520, 880),
    "guessgenre": (400, 720),
    "higherlower": (540, 900),
    "animequiz": (640, 1000),
    "guesswho": (660, 1020),
}
RAID_MODE_DEFAULT = "guesscharacter"
# XP bonus « coup final » (s’ajoute à la part dégâts / MVP / temps), selon difficulté du mode choisi
RAID_XP_FINISHER_BY_MODE: dict[str, int] = {
    "guesscharacter": 12,
    "guessyear": 22,
    "guessepisodes": 22,
    "guessgenre": 12,
    "higherlower": 24,
    "animequiz": 38,
    "guesswho": 40,
}
# Ordre du menu d’inscription : facile → moyen → difficile (pas l’ordre arbitraire du dict).
RAID_MODE_SELECT_ORDER: tuple[str, ...] = (
    "guesscharacter",
    "guessgenre",
    "guessyear",
    "guessepisodes",
    "higherlower",
    "animequiz",
    "guesswho",
)

# Modes à boutons (facile / moyen) : chaque erreur réduit les dégâts si le joueur finit par trouver.
RAID_MODES_WITH_WRONG_PENALTY: frozenset[str] = frozenset({
    "guesscharacter",
    "guessgenre",
    "guessyear",
    "guessepisodes",
    "higherlower",
})

_RAID_JSP_WORDS: frozenset[str] = frozenset(
    {"jsp", "je sais pas", "idk", "skip", "pass", "aucune idée", "dk"}
)


def _raid_wrong_penalty_multiplier(wrongs_before_success: int) -> float:
    """wrongs_before_success = nombre de mauvais clics avant le bon (min 25 % du tirage)."""
    w = max(0, int(wrongs_before_success))
    return max(0.25, 1.0 - 0.22 * w)


def _raid_titles_set_from_media(anime: dict[str, Any]) -> Set[str]:
    """Même logique que Quiz._titles_set (romaji / EN / JP / synonymes)."""
    t = anime.get("title") or {}
    s: Set[str] = set()
    for k in ("romaji", "english", "native"):
        if t.get(k):
            s.add(str(t[k]))
    for syn in (anime.get("synonyms") or []):
        if syn:
            s.add(str(syn))
    return s


def _raid_max_hp_for_players(n: int) -> int:
    """Échelle les PV selon l’équipe (minimum 1 joueur)."""
    n = max(1, int(n))
    return RAID_HP_PER_PLAYER * n
# XP hebdo : base + bonus dégâts + MVP + meilleur temps sur une manche + coup final
RAID_XP_BASE_EACH = 110
RAID_XP_DAMAGE_POOL = 320
RAID_XP_MVP_BONUS = 55
RAID_XP_FASTEST_BONUS = 40


@dataclass
class RaidBattleState:
    guild_id: int
    channel_id: int
    hp: int
    max_hp: int
    round_n: int
    max_rounds: int
    participants: set[int]
    player_modes: dict[int, str] = field(default_factory=dict)
    damage_by_user: dict[int, int] = field(default_factory=dict)
    hits_by_user: dict[int, int] = field(default_factory=dict)
    wrong_by_user: dict[int, int] = field(default_factory=dict)
    best_time_ms: dict[int, int] = field(default_factory=dict)
    final_blow: Optional[tuple[int, str]] = None
    answered_this_round: set[int] = field(default_factory=set)
    round_finished_users: set[int] = field(default_factory=set)
    round_early_scheduled: bool = False
    open_challenge_users: set[int] = field(default_factory=set)
    log_lines: list[str] = field(default_factory=list)
    hub_message: Optional[discord.Message] = None
    hub_view: Any = None
    round_start_ts: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Timer de manche indépendant du View (évite le reset du timeout à chaque edit du message)
    round_timer_task: Optional[asyncio.Task] = field(default=None)
    round_timer_generation: int = 0
    raid_start_ts: float = 0.0
    raid_finished: bool = False
    lang: str = "fr"


def _load_raid_cfg() -> dict[str, Any]:
    return core.load_json(RAID_DATA_PATH, {})


def _save_raid_cfg(data: dict[str, Any]) -> None:
    core.save_json(RAID_DATA_PATH, data)


def _week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _raid_cfg_enabled(c: dict[str, Any]) -> bool:
    """True si le lancement auto raid est activé (tolère JSON mal édité : chaîne « true »/« false »)."""
    v = c.get("enabled")
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "oui", "on")
    return bool(v)


def _raid_datetime_in_timezone(day: date, hour: int, minute: int) -> datetime:
    """Heure locale (BOT_TIMEZONE) pour ce jour + heure — compatible pytz (évite les bugs de combine+tzinfo)."""
    naive = datetime.combine(day, time(hour, minute))
    tz = core.TIMEZONE
    if hasattr(tz, "localize"):
        try:
            return tz.localize(naive, is_dst=None)
        except Exception:
            return tz.localize(naive, is_dst=False)
    return naive.replace(tzinfo=tz)


def _raid_target_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Salon configuré pour le raid (`/raidconfig` → salon), sinon None."""
    cfg = _load_raid_cfg().get(str(guild.id), {})
    cid = cfg.get("channel_id")
    if not cid:
        return None
    ch = guild.get_channel(int(cid))
    if isinstance(ch, discord.TextChannel):
        return ch
    return None


def _next_raid_moment(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    """Prochaine occurrence weekday (0=lun) + heure:minute après `now`."""
    wd = int(weekday) % 7
    for delta in range(14):
        day = (now + timedelta(days=delta)).date()
        if day.weekday() != wd:
            continue
        cand = _raid_datetime_in_timezone(day, hour, minute)
        if cand > now:
            return cand
    return now + timedelta(days=7)


def _resolve_scheduled_raid_for_loop(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    """Créneau T utilisé pour l’alerte 1 h et le lancement auto.

    `_next_raid_moment` utilise `cand > now` : dès **l’heure pile** du raid (ou juste après un
    redémarrage), le « prochain » raid devient **la semaine suivante**, ce qui annule la fenêtre
    d’alerte et peut faire rater le démarrage auto. Tant qu’on est encore dans
    ``[T - 1h, T + 4 min)`` pour un créneau T du calendrier, on retourne ce T.
    """
    wd = int(weekday) % 7
    for delta in range(-7, 15):
        day = (now + timedelta(days=delta)).date()
        if day.weekday() != wd:
            continue
        t = _raid_datetime_in_timezone(day, hour, minute)
        if t - timedelta(hours=1) <= now < t + timedelta(minutes=4):
            return t
    return _next_raid_moment(now, weekday, hour, minute)


def _raid_status_embed(guild: discord.Guild) -> discord.Embed:
    """Embed lisible (thème sombre Discord) pour /raid statut et récap config."""
    cfg = _load_raid_cfg().get(str(guild.id), {})
    ch = cfg.get("channel_id")
    lg = i18n.guild_lang(guild)
    ch_txt = f"<#{ch}>" if ch else _cg(lg, "status_ch_none")
    now = datetime.now(core.TIMEZONE)
    wd = int(cfg.get("weekday", 5))
    h = int(cfg.get("hour", 20))
    mi = int(cfg.get("minute", 0))
    # Même logique que `raid_scheduler` (pas seulement _next_raid_moment).
    nxt = _resolve_scheduled_raid_for_loop(now, wd, h, mi)
    tzname = getattr(core.TIMEZONE, "zone", None) or str(core.TIMEZONE)
    jname = i18n.weekday_name(lg, wd % 7)
    auto = _raid_cfg_enabled(cfg)
    cur_w = _week_key(now)
    rs_w = str(cfg.get("raidstart_week_key") or "")
    ts = int(nxt.timestamp())
    raidstart_val = (
        _cg(lg, "status_raidstart_used", wk=cur_w)
        if rs_w == cur_w
        else _cg(lg, "status_raidstart_ok", wk=cur_w)
    )
    em = discord.Embed(
        title=_cg(lg, "status_title"),
        description=_cg(lg, "status_desc"),
        color=discord.Color.from_rgb(52, 73, 94),
    )
    em.add_field(name=_cg(lg, "status_field_ch"), value=ch_txt, inline=False)
    em.add_field(
        name=_cg(lg, "status_field_slot"),
        value=i18n.t(
            "community_games.status_slot_body",
            lg,
            weekday=jname,
            time=f"{h:02d}:{mi:02d}",
            tz=tzname,
        ),
        inline=True,
    )
    em.add_field(
        name=_cg(lg, "status_field_auto"),
        value=_cg(lg, "status_auto_on") if auto else _cg(lg, "status_auto_off"),
        inline=True,
    )
    em.add_field(
        name=_cg(lg, "status_field_next"),
        value=f"<t:{ts}:F>\n<t:{ts}:R>",
        inline=False,
    )
    if auto and ch:
        alert_dt = nxt - timedelta(hours=1)
        ta = int(alert_dt.timestamp())
        em.add_field(
            name=_cg(lg, "status_field_alert"),
            value=f"<t:{ta}:F>\n<t:{ta}:R>",
            inline=False,
        )
    elif auto and not ch:
        em.add_field(
            name=_cg(lg, "status_field_alert"),
            value=_cg(lg, "status_field_alert_need_ch"),
            inline=False,
        )
    em.add_field(name=_cg(lg, "status_field_raidstart"), value=raidstart_val, inline=False)
    em.set_footer(text=_cg(lg, "status_footer"))
    return em


def _raid_config_instructions_embed(lg: str) -> discord.Embed:
    """Texte d’aide (réf. historique) — préférer le panneau `/raidconfig`."""
    return discord.Embed(
        title=_cg(lg, "config_help_title"),
        description=_cg(lg, "config_help_desc"),
        color=discord.Color.blurple(),
    )


def _raid_config_panel_embed(guild: discord.Guild) -> discord.Embed:
    """Embed du panneau de configuration (même base que le statut + consignes)."""
    lg = i18n.guild_lang(guild)
    em = _raid_status_embed(guild)
    em.title = _cg(lg, "config_panel_title")
    em.description = _cg(lg, "config_panel_desc")
    return em


def _merge_raid_guild_cfg(guild_id: int, **updates: Any) -> dict[str, Any]:
    """Fusionne des clés dans `boss_raid.json` pour une guilde ; retourne l’entrée guilde."""
    with core.DATA_JSON_LOCK:
        cfg = _load_raid_cfg()
        gk = str(guild_id)
        cfg.setdefault(gk, {})
        cur = cfg[gk]
        for k, v in updates.items():
            if v is None:
                continue
            if k == "channel_id":
                cur["channel_id"] = int(v)
            elif k == "enabled":
                cur["enabled"] = bool(v)
            elif k == "weekday":
                cur["weekday"] = int(v)
            elif k == "hour":
                cur["hour"] = int(v)
            elif k == "minute":
                cur["minute"] = int(v)
        _save_raid_cfg(cfg)
        return dict(cfg[gk])


_RE_HHMM = re.compile(r"^\s*([01]?\d|2[0-3])\s*:\s*([0-5]\d)\s*$")


class RaidTimeModal(Modal):
    """Saisie HH:MM (fuseau BOT_TIMEZONE)."""

    def __init__(self, panel: "RaidConfigPanelView") -> None:
        lg = i18n.guild_lang(panel.guild)
        super().__init__(title=_cg(lg, "modal_title"))
        self.panel = panel
        cfg = _load_raid_cfg().get(str(panel.guild.id), {})
        h = int(cfg.get("hour", 20))
        mi = int(cfg.get("minute", 0))
        self.hhmm = TextInput(
            label=_cg(lg, "modal_label"),
            placeholder=_cg(lg, "modal_ph"),
            default=f"{h:02d}:{mi:02d}",
            max_length=5,
            min_length=4,
            required=True,
        )
        self.add_item(self.hhmm)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        if not interaction.guild or interaction.guild.id != self.panel.guild.id:
            await interaction.response.send_message(_cg(lg, "err_invalid_server"), ephemeral=True)
            return
        m = _RE_HHMM.match(self.hhmm.value or "")
        if not m:
            await interaction.response.send_message(
                _cg(lg, "err_hhmm_format"),
                ephemeral=True,
            )
            return
        hour = int(m.group(1))
        minute = int(m.group(2))
        if hour > 23 or minute > 59:
            await interaction.response.send_message(_cg(lg, "err_bad_time"), ephemeral=True)
            return
        _merge_raid_guild_cfg(interaction.guild.id, hour=hour, minute=minute)
        emb = _raid_config_panel_embed(interaction.guild)
        nv = RaidConfigPanelView(self.panel.cog, interaction.guild)
        await interaction.response.edit_message(embed=emb, view=nv)


class RaidConfigPanelView(View):
    """Panneau : salon (liste), jour, heure, minutes, auto on/off, modal HH:MM."""

    def __init__(self, cog: "CommunityGames", guild: discord.Guild) -> None:
        super().__init__(timeout=600.0)
        self.cog = cog
        self.guild = guild
        self._lg = i18n.guild_lang(guild)
        lg = self._lg
        self.add_item(_RaidChannelSelect(self))
        self.add_item(_RaidWeekdaySelect(self))
        self.add_item(_RaidHourSelect(self))
        self.add_item(_RaidMinuteSelect(self))

        b_on = Button(label=_cg(lg, "btn_auto_on"), style=discord.ButtonStyle.success, row=4)
        b_on.callback = self._raid_auto_on  # type: ignore[method-assign]
        self.add_item(b_on)

        b_off = Button(label=_cg(lg, "btn_auto_off"), style=discord.ButtonStyle.danger, row=4)
        b_off.callback = self._raid_auto_off  # type: ignore[method-assign]
        self.add_item(b_off)

        b_hh = Button(label=_cg(lg, "btn_hhmm"), style=discord.ButtonStyle.secondary, row=4)
        b_hh.callback = self._raid_hhmm_modal  # type: ignore[method-assign]
        self.add_item(b_hh)

        b_save = Button(label=_cg(lg, "btn_save"), style=discord.ButtonStyle.success, row=4)
        b_save.callback = self._raid_config_save  # type: ignore[method-assign]
        self.add_item(b_save)

        b_close = Button(label=_cg(lg, "btn_close"), style=discord.ButtonStyle.secondary, row=4)
        b_close.callback = self._raid_config_close  # type: ignore[method-assign]
        self.add_item(b_close)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        lg = i18n.interaction_lang(interaction)
        if not interaction.guild or interaction.guild.id != self.guild.id:
            await interaction.response.send_message(_cg(lg, "err_wrong_guild"), ephemeral=True)
            return False
        m = interaction.guild.get_member(interaction.user.id)
        if not m or not m.guild_permissions.administrator:
            await interaction.response.send_message(_cg(lg, "err_admin"), ephemeral=True)
            return False
        return True

    async def _refresh_panel(self, interaction: discord.Interaction) -> None:
        """Recrée la vue pour rafraîchir les menus (valeurs par défaut à jour)."""
        emb = _raid_config_panel_embed(self.guild)
        nv = RaidConfigPanelView(self.cog, self.guild)
        await interaction.response.edit_message(embed=emb, view=nv)

    async def _raid_auto_on(self, interaction: discord.Interaction) -> None:
        _merge_raid_guild_cfg(self.guild.id, enabled=True)
        await self._refresh_panel(interaction)

    async def _raid_auto_off(self, interaction: discord.Interaction) -> None:
        _merge_raid_guild_cfg(self.guild.id, enabled=False)
        await self._refresh_panel(interaction)

    async def _raid_hhmm_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RaidTimeModal(self))

    async def _raid_config_save(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        await interaction.response.defer(ephemeral=True)
        msg = interaction.message
        if msg is not None:
            if isinstance(msg.channel, discord.Thread):
                await interaction.followup.delete_message(msg.id, thread=msg.channel)
            else:
                await interaction.followup.delete_message(msg.id)
        await interaction.followup.send(
            _cg(lg, "raid_save_ok"),
            ephemeral=True,
        )

    async def _raid_config_close(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        msg = interaction.message
        if msg is not None:
            if isinstance(msg.channel, discord.Thread):
                await interaction.followup.delete_message(msg.id, thread=msg.channel)
            else:
                await interaction.followup.delete_message(msg.id)


class _RaidChannelSelect(ChannelSelect):
    def __init__(self, panel: RaidConfigPanelView) -> None:
        lg = i18n.guild_lang(panel.guild)
        super().__init__(
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            placeholder=_cg(lg, "ph_channel"),
            min_values=1,
            max_values=1,
            row=0,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        ch = self.values[0]
        # NewsChannel (annonces) n’est pas un TextChannel — éviter isinstance(..., TextChannel) seul.
        ch_type = getattr(ch, "type", None)
        if ch_type not in (discord.ChannelType.text, discord.ChannelType.news):
            await interaction.response.send_message(_cg(lg, "err_text_channel"), ephemeral=True)
            return
        if ch.guild.id != self.panel.guild.id:
            await interaction.response.send_message(_cg(lg, "err_channel_this_guild"), ephemeral=True)
            return
        _merge_raid_guild_cfg(self.panel.guild.id, channel_id=ch.id)
        await self.panel._refresh_panel(interaction)


class _RaidWeekdaySelect(Select):
    def __init__(self, panel: RaidConfigPanelView) -> None:
        cfg = _load_raid_cfg().get(str(panel.guild.id), {})
        cur_wd = int(cfg.get("weekday", 5)) % 7
        _lg = i18n.guild_lang(panel.guild)
        opts = [
            discord.SelectOption(
                label=i18n.weekday_name(_lg, i),
                value=str(i),
                default=(i == cur_wd),
            )
            for i in range(7)
        ]
        super().__init__(
            placeholder=_cg(_lg, "ph_weekday"),
            min_values=1,
            max_values=1,
            options=opts,
            row=1,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        wd = int(self.values[0])
        _merge_raid_guild_cfg(self.panel.guild.id, weekday=wd)
        await self.panel._refresh_panel(interaction)


class _RaidHourSelect(Select):
    def __init__(self, panel: RaidConfigPanelView) -> None:
        lg = i18n.guild_lang(panel.guild)
        cfg = _load_raid_cfg().get(str(panel.guild.id), {})
        cur_h = int(cfg.get("hour", 20)) % 24
        opts = [
            discord.SelectOption(
                label=f"{h:02d} h",
                value=str(h),
                default=(h == cur_h),
            )
            for h in range(24)
        ]
        super().__init__(
            placeholder=_cg(lg, "ph_hour"),
            min_values=1,
            max_values=1,
            options=opts,
            row=2,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        h = int(self.values[0])
        _merge_raid_guild_cfg(self.panel.guild.id, hour=h)
        await self.panel._refresh_panel(interaction)


class _RaidMinuteSelect(Select):
    """Minutes par pas de 5 (Discord limite 25 options par liste)."""

    def __init__(self, panel: RaidConfigPanelView) -> None:
        cfg = _load_raid_cfg().get(str(panel.guild.id), {})
        cur_mi = int(cfg.get("minute", 0)) % 60
        steps = list(range(0, 60, 5))
        nearest = min(steps, key=lambda x: abs(x - cur_mi))
        opts = [
            discord.SelectOption(
                label=f":{m:02d}",
                value=str(m),
                default=(m == nearest),
            )
            for m in steps
        ]
        super().__init__(
            placeholder=_cg(i18n.guild_lang(panel.guild), "ph_minute"),
            min_values=1,
            max_values=1,
            options=opts,
            row=3,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        mi = int(self.values[0])
        _merge_raid_guild_cfg(self.panel.guild.id, minute=mi)
        await self.panel._refresh_panel(interaction)


def _raidstart_week_available(guild_id: int) -> bool:
    """True si `/raidstart` n’a pas encore été consommé pour la semaine ISO courante."""
    cfg = _load_raid_cfg()
    last = str(cfg.get(str(guild_id), {}).get("raidstart_week_key") or "")
    cur = _week_key(datetime.now(core.TIMEZONE))
    return last != cur


class RaidStartConfirmView(View):
    """Confirmation éphémère : l’admin accepte la limite 1× / semaine avant lancement."""

    def __init__(
        self,
        cog: "CommunityGames",
        guild: discord.Guild,
        target: discord.TextChannel,
        week_key: str,
        invoker_id: int,
    ) -> None:
        super().__init__(timeout=120.0)
        self.cog = cog
        self.guild = guild
        self.target = target
        self.week_key = week_key
        self.invoker_id = invoker_id
        self._lg = i18n.guild_lang(guild)
        lg = self._lg
        b_ok = Button(label=_cg(lg, "btn_confirm_start"), style=discord.ButtonStyle.success, row=0)
        b_ok.callback = self.confirm  # type: ignore[method-assign]
        self.add_item(b_ok)
        b_x = Button(label=_cg(lg, "btn_cancel"), style=discord.ButtonStyle.secondary, row=0)
        b_x.callback = self.cancel  # type: ignore[method-assign]
        self.add_item(b_x)

    async def confirm(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(_cg(lg, "raid_invite_nope"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if _active_raids.get(self.guild.id):
            await interaction.followup.send(_cg(lg, "raid_already_running"), ephemeral=True)
            return
        cur_key = _week_key(datetime.now(core.TIMEZONE))
        cfg = _load_raid_cfg()
        gk = str(self.guild.id)
        if str(cfg.get(gk, {}).get("raidstart_week_key") or "") == cur_key:
            await interaction.followup.send(
                _cg(lg, "raid_week_limit_hit"),
                ephemeral=True,
            )
            return
        await self.cog._start_boss_raid(self.guild, self.target, self.week_key)
        with core.DATA_JSON_LOCK:
            cfg = _load_raid_cfg()
            cfg.setdefault(gk, {})
            cfg[gk]["raidstart_week_key"] = cur_key
            _save_raid_cfg(cfg)
        await interaction.followup.send(
            _cg(lg, "raid_start_ok", mention=self.target.mention, wk=cur_key),
            ephemeral=True,
        )
        self.stop()
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        try:
            if interaction.message:
                await interaction.message.edit(view=self)
        except Exception:
            pass

    async def cancel(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(_cg(lg, "raid_invite_nope"), ephemeral=True)
            return
        self.stop()
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        try:
            await interaction.response.edit_message(
                content=_cg(lg, "raid_cancel_embed"),
                embed=None,
                view=self,
            )
        except Exception:
            await interaction.response.send_message(_cg(lg, "raid_cancel_short"), ephemeral=True)


# ---------- Boss raid : combat (v2) ----------


def _raid_hp_bar(hp: int, max_hp: int, width: int = 18) -> str:
    return pct_bar_blocks(hp, max_hp, width)


def _raid_hp_pct(hp: int, max_hp: int) -> int:
    if max_hp <= 0:
        return 0
    return int(max(0, min(100, round(100 * hp / max_hp))))


def _raid_boss_phase(pct: int, lg: str) -> tuple[str, str]:
    """(emoji titre, phrase d’ambiance) selon les PV restants."""
    if pct <= 0:
        return "🏆", _cg(lg, "phase_victory")
    if pct <= 12:
        return "💀", _cg(lg, "phase_low")
    if pct <= 35:
        return "🔥", _cg(lg, "phase_mid")
    if pct <= 60:
        return "⚔️", _cg(lg, "phase_high")
    return "🛡️", _cg(lg, "phase_full")


def _raid_embed_color_for_hp(pct: int) -> discord.Color:
    """Couleur du embed : vert → orange → rouge selon l’urgence."""
    if pct <= 15:
        return discord.Color.from_rgb(200, 40, 40)
    if pct <= 40:
        return discord.Color.from_rgb(220, 120, 40)
    if pct <= 70:
        return discord.Color.from_rgb(180, 160, 50)
    return discord.Color.from_rgb(60, 140, 80)


class RaidModeSelect(Select):
    """Menu : mode de défi pour tout le raid (une fois choisi, inchangé)."""

    def __init__(self, host: "RaidModeSelectView") -> None:
        self.host = host
        lang = host.lang
        opts = []
        for k in RAID_MODE_SELECT_ORDER:
            if k not in RAID_DAMAGE_BY_MODE:
                continue
            tier = _raid_tier_label(k, lang)
            lbl = _raid_mode_label(k, lang)
            label = f"{tier} · {lbl}"[:100]
            lo, hi = RAID_DAMAGE_BY_MODE[k]
            fin = RAID_XP_FINISHER_BY_MODE.get(k, 0)
            desc = i18n.t("raid.mode_desc", lang, lo=lo, hi=hi, fin=fin)[:100]
            opts.append(discord.SelectOption(label=label, value=k, description=desc))
        super().__init__(
            placeholder=i18n.t("raid.select_placeholder", lang)[:150],
            min_values=1,
            max_values=1,
            options=opts,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        lg = self.host.lang
        if interaction.user.id != self.host.picker_id:
            await interaction.response.send_message(_cg(lg, "mode_not_yours"), ephemeral=True)
            return
        if self.host.picker_id in self.host.join_view.mode_by_user:
            await interaction.response.send_message(
                _cg(lg, "mode_already"),
                ephemeral=True,
            )
            return
        mode = (self.values[0] if self.values else RAID_MODE_DEFAULT) or RAID_MODE_DEFAULT
        self.host.join_view.mode_by_user[self.host.picker_id] = mode
        label = _raid_mode_label(mode, self.host.lang)
        tier = _raid_tier_label(mode, self.host.lang)
        lo, hi = RAID_DAMAGE_BY_MODE.get(mode, (400, 720))
        fin = RAID_XP_FINISHER_BY_MODE.get(mode, 12)
        await interaction.response.edit_message(
            content=_cg(
                lg,
                "mode_saved",
                label=label,
                tier=tier,
                lo=lo,
                hi=hi,
                fin=fin,
            ),
            embed=None,
            view=None,
        )
        self.host.stop()


class RaidModeSelectView(View):
    def __init__(self, join_view: "RaidJoinView", picker_id: int, lang: str) -> None:
        super().__init__(timeout=RAID_JOIN_SECONDS)
        self.join_view = join_view
        self.picker_id = picker_id
        self.lang = lang
        self.add_item(RaidModeSelect(self))


class RaidJoinView(View):
    """Inscription avant le combat (salon public).

    Le délai d’inscription est géré par une tâche asyncio **fixe** (voir `_schedule_raid_join_phase_end`) :
    avec `timeout` sur le View, discord.py **réinitialise** le compteur à **chaque** clic sur le bouton,
    ce qui peut repousser la fin indéfiniment (ex. plusieurs inscriptions sur plusieurs minutes).
    """

    def __init__(self, cog: "CommunityGames", guild_id: int, channel_id: int) -> None:
        # Pas de timeout lib : la fin de phase est déclenchée par `asyncio.sleep(RAID_JOIN_SECONDS)` au lancement.
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.joined: set[int] = set()
        self.mode_by_user: dict[int, str] = {}
        self.message: Optional[discord.Message] = None
        self.promo_message: Optional[discord.Message] = None
        self._join_lock = asyncio.Lock()
        self._raid_join_timer_task: Optional[asyncio.Task[None]] = None
        g = cog.bot.get_guild(guild_id)
        _lg = i18n.guild_lang(g) if g else "fr"
        b = Button(label=_cg(_lg, "join_btn"), style=discord.ButtonStyle.success)
        b.callback = self.join  # type: ignore[method-assign]
        self.add_item(b)

    async def join(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(_cg(lg, "err_wrong_guild"), ephemeral=True)
            return
        uid = interaction.user.id
        async with self._join_lock:
            if uid in self.joined:
                await interaction.response.send_message(
                    _cg(lg, "join_already"),
                    ephemeral=True,
                )
                return
            self.joined.add(uid)
            n = len(self.joined)
        await interaction.response.send_message(
            _cg(lg, "join_ok", n=n),
            ephemeral=True,
        )
        g = self.cog.bot.get_guild(self.guild_id)
        _lang = i18n.guild_lang(g) if g else "fr"
        default_lbl = _raid_mode_label(RAID_MODE_DEFAULT, _lang)
        em = discord.Embed(
            title=_cg(_lang, "join_embed_title"),
            description=_cg(_lang, "join_embed_desc", default_mode=default_lbl),
            color=discord.Color.dark_red(),
        )
        await interaction.followup.send(
            embed=em,
            view=RaidModeSelectView(self, uid, _lang),
            ephemeral=True,
        )


class RaidRoundHubView(View):
    """Message public : bouton pour recevoir un défi perso (éphemeral)."""

    def __init__(self, cog: "CommunityGames", state: RaidBattleState) -> None:
        # Pas de timeout sur le View : le délai de manche est géré par asyncio (voir _raid_round_timer)
        super().__init__(timeout=None)
        self.cog = cog
        self.state = state
        self.ended = False
        lg = state.lang
        b = Button(label=_cg(lg, "hub_btn"), style=discord.ButtonStyle.secondary)
        b.callback = self.get_challenge  # type: ignore[method-assign]
        self.add_item(b)

    async def get_challenge(self, interaction: discord.Interaction) -> None:
        lg = self.state.lang
        if self.ended or self.state.hp <= 0:
            await interaction.response.send_message(_cg(lg, "hub_round_over"), ephemeral=True)
            return
        if not interaction.guild or interaction.guild.id != self.state.guild_id:
            await interaction.response.send_message(_cg(lg, "err_wrong_guild"), ephemeral=True)
            return
        uid = interaction.user.id
        if uid not in self.state.participants:
            await interaction.response.send_message(
                _cg(lg, "hub_not_participant"),
                ephemeral=True,
            )
            return
        if uid in self.state.round_finished_users:
            await interaction.response.send_message(
                _cg(lg, "hub_round_done"),
                ephemeral=True,
            )
            return
        if uid in self.state.open_challenge_users:
            await interaction.response.send_message(
                _cg(lg, "hub_has_challenge"),
                ephemeral=True,
            )
            return

        ok_burst, retry_c = abuse.allow_component_burst(uid, f"raid_hub:{self.state.guild_id}")
        if not ok_burst:
            await interaction.response.send_message(
                _cg(lg, "hub_burst", s=max(1, int(retry_c) + 1)),
                ephemeral=True,
            )
            return

        mode = self.state.player_modes.get(uid, RAID_MODE_DEFAULT)
        quiz, attach = await self.cog._raid_build_challenge(
            mode, self.state.round_n, self.state.max_rounds, lg
        )
        if not quiz:
            await interaction.response.send_message(_cg(lg, "hub_load_fail"), ephemeral=True)
            return

        lo, hi = RAID_DAMAGE_BY_MODE.get(mode, RAID_DAMAGE_BY_MODE[RAID_MODE_DEFAULT])
        damage = random.randint(lo, hi)
        async with self.state.lock:
            self.state.open_challenge_users.add(uid)

        try:
            if str(quiz.get("kind") or "") == "guesswho_text":
                emb = discord.Embed(
                    title=_cg(lg, "emb_gw_title"),
                    description=quiz.get("prompt", "").strip() or _cg(lg, "emb_gw_fallback"),
                    color=discord.Color.dark_red(),
                )
                if quiz.get("image_url"):
                    emb.set_image(url=quiz["image_url"])
                send_kw: dict[str, Any] = {"embed": emb, "ephemeral": True}
                if attach is not None:
                    send_kw["file"] = attach
                await interaction.response.send_message(**send_kw)
                asyncio.create_task(
                    self.cog._raid_run_guesswho_text(
                        interaction,
                        self.state,
                        self,
                        uid,
                        quiz,
                        damage,
                        mode,
                    )
                )
                return

            if str(quiz.get("kind") or "") == "animequiz_text":
                emb = discord.Embed(
                    title=_cg(lg, "emb_aq_title"),
                    description=quiz.get("prompt", "").strip() or _cg(lg, "emb_aq_fallback"),
                    color=discord.Color.dark_red(),
                )
                if quiz.get("image_url"):
                    emb.set_image(url=quiz["image_url"])
                await interaction.response.send_message(embed=emb, ephemeral=True)
                asyncio.create_task(
                    self.cog._raid_run_animequiz_text(
                        interaction,
                        self.state,
                        self,
                        uid,
                        quiz,
                        damage,
                        mode,
                    )
                )
                return

            pv = PersonalRaidChallengeView(
                cog=self.cog,
                state=self.state,
                hub=self,
                user_id=uid,
                quiz=quiz,
                damage=damage,
                raid_mode=mode,
            )
            if str(quiz.get("kind") or "") == "higherlower":
                emb = discord.Embed(
                    title=_cg(lg, "emb_hl_title"),
                    description=quiz.get("prompt", "").strip() or _cg(lg, "emb_hl_fallback"),
                    color=discord.Color.orange(),
                )
            else:
                emb = discord.Embed(
                    title=_cg(lg, "emb_generic_title"),
                    description=quiz.get("prompt", "").strip() or _cg(lg, "emb_generic_fallback"),
                    color=discord.Color.dark_red(),
                )
            if quiz.get("image_url"):
                emb.set_image(url=quiz["image_url"])
            send_kw = {"embed": emb, "view": pv, "ephemeral": True}
            if attach is not None:
                send_kw["file"] = attach
            await interaction.response.send_message(**send_kw)
        except Exception:
            async with self.state.lock:
                self.state.open_challenge_users.discard(uid)
            raise


class PersonalRaidChallengeView(View):
    """Boutons de choix — message éphémère du joueur (mode raid variable)."""

    def __init__(
        self,
        *,
        cog: "CommunityGames",
        state: RaidBattleState,
        hub: RaidRoundHubView,
        user_id: int,
        quiz: dict[str, Any],
        damage: int,
        raid_mode: str,
    ) -> None:
        super().__init__(timeout=RAID_ROUND_SECONDS)
        self.cog = cog
        self.state = state
        self.hub = hub
        self.user_id = user_id
        self.quiz = quiz
        self.options = list(quiz.get("options") or [])
        self.correct_index = int(quiz.get("correct_index", 0))
        self.correct_name = str(quiz.get("correct_name", "?"))
        self.anime_hint = str(quiz.get("anime_hint", ""))
        self.damage = damage
        self.raid_mode = raid_mode
        self._lang = state.lang
        self.t0 = monotonic()
        self.resolved = False
        self.wrong_clicks = 0

        for i, label in enumerate(self.options):
            b = Button(label=str(label)[:79], style=discord.ButtonStyle.primary, row=i // 2)
            b.callback = self._make_cb(i)
            self.add_item(b)

    def _make_cb(self, idx: int):
        async def _cb(interaction: discord.Interaction) -> None:
            await self._handle(interaction, idx)

        return _cb

    def _applies_wrong_penalty(self) -> bool:
        return self.raid_mode in RAID_MODES_WITH_WRONG_PENALTY

    def _success_lines(self, dt_ms: int, eff_damage: int, mult: float) -> str:
        lg = self._lang
        extra = str(self.quiz.get("success_extra") or "").strip()
        kind = str(self.quiz.get("kind") or "")
        if kind == "higherlower" and not extra:
            t1 = self.quiz.get("hl_title1", "?")
            t2 = self.quiz.get("hl_title2", "?")
            p1 = self.quiz.get("hl_pop1", 0)
            p2 = self.quiz.get("hl_pop2", 0)
            extra = f"**{t1}** ({p1}) vs **{t2}** ({p2})"
        head = f"✅ **{self.correct_name}**"
        if self.anime_hint and self.anime_hint != "—":
            head += f" — _{self.anime_hint}_"
        lines = [head]
        if extra:
            lines.append(extra)
        lines.append(_cg(lg, "success_dmg", dmg=eff_damage, ms=dt_ms))
        if self._applies_wrong_penalty() and self.wrong_clicks > 0 and mult < 0.999:
            lines.append(
                _cg(
                    lg,
                    "success_penalty",
                    base=self.damage,
                    mult=mult,
                    w=self.wrong_clicks,
                )
            )
        return "\n".join(lines)

    async def _handle(self, interaction: discord.Interaction, idx: int) -> None:
        lg = self._lang
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(_cg(lg, "not_your_challenge"), ephemeral=True)
            return
        if self.resolved:
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                pass
            return

        if idx != self.correct_index:
            self.wrong_clicks += 1
            async with self.state.lock:
                self.state.wrong_by_user[self.user_id] = self.state.wrong_by_user.get(self.user_id, 0) + 1
                disp = getattr(interaction.user, "display_name", None) or str(interaction.user)
                ml = _raid_mode_label(self.raid_mode, lg)
                self.state.log_lines = self.state.log_lines[-14:] + [
                    _cg(lg, "log_wrong_btn", name=disp, mode=ml, n=self.wrong_clicks)
                ]
            for i, child in enumerate(self.children):
                if isinstance(child, Button) and i == idx:
                    child.disabled = True
                    break
            await interaction.response.edit_message(view=self)
            ch = self.cog.bot.get_channel(self.state.channel_id)
            if isinstance(ch, discord.TextChannel):
                await self.cog._raid_refresh_hub(self.state)
            return

        dt_ms = int((monotonic() - self.t0) * 1000)
        self.resolved = True
        mult = 1.0
        if self._applies_wrong_penalty() and self.wrong_clicks > 0:
            mult = _raid_wrong_penalty_multiplier(self.wrong_clicks)
        eff_damage = max(1, int(round(self.damage * mult)))
        applied = await self.cog._raid_register_hit(
            interaction.user,
            self.state,
            eff_damage,
            dt_ms,
            self.hub,
            self.raid_mode,
        )
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        if not applied:
            await interaction.response.edit_message(
                content=_cg(lg, "boss_dead_answer"),
                embed=None,
                view=self,
                attachments=[],
            )
            return
        await interaction.response.edit_message(
            content=self._success_lines(dt_ms, eff_damage, mult),
            embed=None,
            view=self,
            attachments=[],
        )

    async def on_timeout(self) -> None:
        if self.state.raid_finished or self.state.hp <= 0:
            return
        if not _active_raids.get(self.state.guild_id):
            return
        ch = self.cog.bot.get_channel(self.state.channel_id)
        nm = "?"
        if isinstance(ch, discord.TextChannel) and ch.guild:
            mb = ch.guild.get_member(self.user_id)
            if mb:
                nm = mb.display_name
        async with self.state.lock:
            self.state.open_challenge_users.discard(self.user_id)
            self.state.round_finished_users.add(self.user_id)
            g = self.cog.bot.get_guild(self.state.guild_id)
            _lg = i18n.guild_lang(g) if g else "fr"
            ml = _raid_mode_label(self.raid_mode, _lg)
            self.state.log_lines = self.state.log_lines[-14:] + [
                _cg(_lg, "log_timeout_mode", name=nm, mode=ml)
            ]
        if isinstance(ch, discord.TextChannel):
            await self.cog._raid_refresh_hub(self.state)
            await self.cog._raid_maybe_finish_round_early(self.state, self.hub)


class CommunityGames(commands.Cog):
    """Raid boss, chain quiz, guesswho."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Évite de spammer les logs si l’alerte est skip (déjà marquée pour la semaine).
        self._raid_alert_skip_logged: set[str] = set()
        self._raid_cross_guild_logged: set[str] = set()

    async def cog_load(self) -> None:
        self.raid_scheduler.start()

    async def cog_unload(self) -> None:
        self.raid_scheduler.cancel()

    # ---------- Raid : logique ----------

    async def _raid_fetch_char_quiz(self) -> Optional[dict[str, Any]]:
        page = random.randint(1, 100)
        query = """
        query ($page: Int) {
          Page(page: $page, perPage: 4) {
            characters(sort: FAVOURITES_DESC) {
              name { full }
              image { large }
              media(type: ANIME) { nodes { title { romaji } } }
            }
          }
        }
        """
        data = await core.query_anilist_async(query, {"page": page})
        if not data or "data" not in data:
            return None
        chars = data["data"]["Page"]["characters"]
        if len(chars) < 4:
            return None
        correct = random.choice(chars)
        correct_name = correct["name"]["full"]
        img = (correct.get("image") or {}).get("large")
        nodes = (correct.get("media") or {}).get("nodes") or []
        anime_hint = (nodes[0]["title"]["romaji"] if nodes else "—")
        options = [c["name"]["full"] for c in chars]
        random.shuffle(options)
        try:
            correct_index = options.index(correct_name)
        except ValueError:
            correct_index = 0
        return {
            "kind": "guesscharacter",
            "options": options,
            "correct_index": correct_index,
            "correct_name": correct_name,
            "anime_hint": anime_hint,
            "image_url": img,
        }

    def _raid_pick_wrong_years(self, correct: int, n: int = 3) -> list[int]:
        out: set[int] = set()
        guard = 0
        while len(out) < n and guard < 80:
            guard += 1
            delta = random.randint(-28, 28)
            y = correct + delta
            if y != correct and 1960 <= y <= datetime.now().year + 1:
                out.add(y)
        while len(out) < n:
            out.add(correct + 7 + len(out))
        return list(out)[:n]

    async def _raid_build_challenge(
        self,
        mode: str,
        round_n: int,
        max_rounds: int,
        lg: str,
    ) -> tuple[Optional[dict[str, Any]], Optional[discord.File]]:
        m = mode if mode in RAID_DAMAGE_BY_MODE else RAID_MODE_DEFAULT
        rn, mr = int(round_n), int(max_rounds)

        if m == "guesscharacter":
            q = await self._raid_fetch_char_quiz()
            if not q:
                return None, None
            q["prompt"] = _cg(
                lg,
                "challenge_gc",
                rn=rn,
                mr=mr,
                hint=q.get("anime_hint", "—"),
            )
            return q, None

        if m == "guessyear":
            page = random.randint(1, 400)
            query = """
            query ($page: Int) {
              Page(perPage: 1, page: $page) {
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                  title { romaji }
                  startDate { year }
                  coverImage { extraLarge }
                }
              }
            }
            """
            data = await core.query_anilist_async(query, {"page": page})
            try:
                anime = data["data"]["Page"]["media"][0]
                title = (anime.get("title") or {}).get("romaji") or "?"
                year = (anime.get("startDate") or {}).get("year")
            except Exception:
                return None, None
            if not year:
                return None, None
            year = int(year)
            wrong = self._raid_pick_wrong_years(year, 3)
            options = [year] + wrong
            random.shuffle(options)
            quiz = {
                "kind": "guessyear",
                "options": [str(x) for x in options],
                "correct_index": options.index(year),
                "correct_name": str(year),
                "anime_hint": title,
                "image_url": (anime.get("coverImage") or {}).get("extraLarge"),
                "prompt": _cg(lg, "challenge_gy", rn=rn, mr=mr, title=title),
            }
            return quiz, None

        if m == "guessepisodes":
            anime = None
            for _ in range(6):
                page = random.randint(1, 400)
                query = """
                query ($page: Int) {
                  Page(perPage: 1, page: $page) {
                    media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                      title { romaji }
                      episodes
                      coverImage { extraLarge }
                    }
                  }
                }
                """
                data = await core.query_anilist_async(query, {"page": page})
                try:
                    cand = data["data"]["Page"]["media"][0]
                    ep = cand.get("episodes")
                    if ep and isinstance(ep, int):
                        anime = cand
                        break
                except Exception:
                    continue
            if not anime:
                return None, None
            title = (anime.get("title") or {}).get("romaji") or "?"
            episodes = int(anime["episodes"])
            candidates: list[int] = [episodes]
            guard = 0
            while len(candidates) < 4 and guard < 80:
                guard += 1
                alt = max(1, episodes + random.randint(-22, 22))
                if alt not in candidates:
                    candidates.append(alt)
            options = candidates[:4]
            random.shuffle(options)
            quiz = {
                "kind": "guessepisodes",
                "options": [str(x) for x in options],
                "correct_index": options.index(episodes),
                "correct_name": str(episodes),
                "anime_hint": title,
                "image_url": (anime.get("coverImage") or {}).get("extraLarge"),
                "prompt": _cg(lg, "challenge_ge", rn=rn, mr=mr, title=title),
            }
            return quiz, None

        if m == "guessgenre":
            anime = None
            for _ in range(6):
                page = random.randint(1, 400)
                query = """
                query ($page: Int) {
                  Page(perPage: 1, page: $page) {
                    media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                      title { romaji }
                      genres
                      coverImage { extraLarge }
                    }
                  }
                }
                """
                data = await core.query_anilist_async(query, {"page": page})
                try:
                    cand = data["data"]["Page"]["media"][0]
                    if cand.get("genres"):
                        anime = cand
                        break
                except Exception:
                    continue
            if not anime:
                return None, None
            title = (anime.get("title") or {}).get("romaji") or "?"
            genres = list(anime.get("genres") or [])
            correct = random.choice(genres)
            pool_extra = [
                "Psychological", "Sports", "Music", "Mecha", "Military",
                "Historical", "Samurai", "Thriller", "Horror", "Mystery",
            ]
            wrong: list[str] = []
            for g in pool_extra:
                if g not in genres and g != correct:
                    wrong.append(g)
                if len(wrong) >= 3:
                    break
            for g in genres:
                if g != correct and len(wrong) < 3:
                    wrong.append(g)
            options = [correct] + wrong[:3]
            filler = [
                "Isekai", "Mystery", "School", "Supernatural", "Kids",
                "Shounen", "Shoujo", "Seinen", "Josei", "Dementia",
            ]
            for g in filler:
                if len(options) >= 4:
                    break
                if g not in options and g not in genres:
                    options.append(g)
            options = options[:4]
            random.shuffle(options)
            quiz = {
                "kind": "guessgenre",
                "options": options,
                "correct_index": options.index(correct),
                "correct_name": correct,
                "anime_hint": title,
                "image_url": (anime.get("coverImage") or {}).get("extraLarge"),
                "prompt": _cg(lg, "challenge_gg", rn=rn, mr=mr, title=title),
            }
            return quiz, None

        if m == "higherlower":
            page = random.randint(1, 20)
            query = """
            query ($page: Int) {
              Page(perPage: 50, page: $page) {
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                  title { romaji }
                  popularity
                  coverImage { extraLarge }
                }
              }
            }
            """
            data = await core.query_anilist_async(query, {"page": page})
            try:
                medias = data["data"]["Page"]["media"]
            except Exception:
                return None, None
            if not medias or len(medias) < 2:
                return None, None
            a, b = random.sample(medias, 2)
            t1 = (a.get("title") or {}).get("romaji") or "?"
            t2 = (b.get("title") or {}).get("romaji") or "?"
            p1 = int(a.get("popularity") or 0)
            p2 = int(b.get("popularity") or 0)
            correct_index = 0 if p1 >= p2 else 1
            winner = t1 if correct_index == 0 else t2
            hl_file = await higherlower_combine.make_higherlower_combined_file(
                a, b, filename="raid_higherlower.png"
            )
            quiz = {
                "kind": "higherlower",
                "options": [f"1️⃣ {t1[:60]}", f"2️⃣ {t2[:60]}"],
                "correct_index": correct_index,
                "correct_name": _cg(lg, "hl_pop_label", winner=winner),
                "anime_hint": _cg(lg, "hl_anilist"),
                "image_url": ("attachment://raid_higherlower.png" if hl_file else None),
                "hl_title1": t1,
                "hl_title2": t2,
                "hl_pop1": p1,
                "hl_pop2": p2,
                "prompt": _cg(lg, "challenge_hl", rn=rn, mr=mr, t1=t1, t2=t2),
            }
            return quiz, hl_file

        if m == "animequiz":
            page = random.randint(1, 80)
            query = """
            query ($page: Int) {
              Page(page: $page, perPage: 8) {
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                  title { romaji english native }
                  synonyms
                  coverImage { extraLarge large }
                }
              }
            }
            """
            data = await core.query_anilist_async(query, {"page": page})
            try:
                medias = data["data"]["Page"]["media"]
            except Exception:
                return None, None
            if not medias:
                return None, None
            correct = random.choice(medias)
            ctitle = (correct.get("title") or {}).get("romaji") or "?"
            img = (correct.get("coverImage") or {}).get("extraLarge") or (correct.get("coverImage") or {}).get("large")
            quiz = {
                "kind": "animequiz_text",
                "media": correct,
                "correct_romaji": ctitle,
                "anime_hint": "—",
                "image_url": img,
                "prompt": _cg(lg, "challenge_aq", rn=rn, mr=mr, secs=int(RAID_ROUND_SECONDS)),
            }
            return quiz, None

        if m == "guesswho":
            page = random.randint(1, 100)
            query = """
            query ($page: Int) {
              Page(page: $page, perPage: 1) {
                characters(sort: FAVOURITES_DESC) {
                  name { full }
                  image { large }
                  media(type: ANIME) { nodes { title { romaji } } }
                }
              }
            }
            """
            data = await core.query_anilist_async(query, {"page": page})
            if not data or "data" not in data:
                return None, None
            chars = data["data"]["Page"]["characters"]
            if not chars:
                return None, None
            correct = chars[0]
            correct_name = correct["name"]["full"]
            url = (correct.get("image") or {}).get("large")
            nodes = (correct.get("media") or {}).get("nodes") or []
            anime_hint = (nodes[0]["title"]["romaji"] if nodes else "—")
            div, blur_r, _gw_to, _xp = GUESSWHO_MODES.get("medium", GUESSWHO_MODES["medium"])
            quiz = {
                "kind": "guesswho_text",
                "correct_name": correct_name,
                "anime_hint": anime_hint,
                "image_url": "attachment://raid_guesswho.png",
                "prompt": _cg(
                    lg,
                    "challenge_gw",
                    rn=rn,
                    mr=mr,
                    hint=anime_hint,
                    secs=int(RAID_ROUND_SECONDS),
                ),
            }
            if not url:
                quiz["image_url"] = None
                return quiz, None
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        raw = await resp.read()
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                d = max(3, int(div))
                im = im.resize((max(32, im.width // d), max(32, im.height // d)), Image.Resampling.LANCZOS)
                im = im.resize((im.width * d, im.height * d), Image.Resampling.NEAREST)
                im = im.filter(ImageFilter.GaussianBlur(radius=float(blur_r)))
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                buf.seek(0)
                return quiz, discord.File(buf, filename="raid_guesswho.png")
            except Exception:
                LOG.warning("raid guesswho blur failed", exc_info=True)
                quiz["image_url"] = (correct.get("image") or {}).get("large")
                return quiz, None

        q = await self._raid_fetch_char_quiz()
        if not q:
            return None, None
        q["prompt"] = _cg(
            lg,
            "challenge_gc",
            rn=rn,
            mr=mr,
            hint=q.get("anime_hint", "—"),
        )
        return q, None

    def _raid_hub_embed(self, state: RaidBattleState) -> discord.Embed:
        lg = state.lang
        bar = _raid_hp_bar(state.hp, state.max_hp)
        pct = _raid_hp_pct(state.hp, state.max_hp)
        phase_emoji, phase_line = _raid_boss_phase(pct, lg)
        total_dmg = sum(state.damage_by_user.values())
        lines = [
            _cg(lg, "hub_line_hp", emoji=phase_emoji, hp=state.hp, maxhp=state.max_hp, pct=pct),
            _cg(lg, "hub_line_bar", bar=bar),
            f"_{phase_line}_",
            "",
            _cg(lg, "hub_dmg_total", dmg=total_dmg, n=len(state.participants)),
            "",
            _cg(
                lg,
                "hub_round_line",
                cur=state.round_n,
                mx=state.max_rounds,
                secs=int(RAID_ROUND_SECONDS),
            ),
        ]
        if state.log_lines:
            lines.append("")
            lines.append(_cg(lg, "hub_journal"))
            lines.extend(state.log_lines[-8:])
        return discord.Embed(
            title=_cg(lg, "hub_title", emoji=phase_emoji, cur=state.round_n, mx=state.max_rounds),
            description="\n".join(lines),
            color=_raid_embed_color_for_hp(pct),
        )

    async def _raid_cancel_round_timer_async(self, state: RaidBattleState) -> None:
        t = state.round_timer_task
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        state.round_timer_task = None

    async def _raid_round_timer_worker(
        self,
        state: RaidBattleState,
        channel: discord.TextChannel,
        gen: int,
    ) -> None:
        """Fin de manche si le délai est écoulé (non réinitialisé par les edits du message hub)."""
        try:
            await asyncio.sleep(RAID_ROUND_SECONDS)
        except asyncio.CancelledError:
            return
        if state.round_timer_generation != gen:
            return
        if not _active_raids.get(state.guild_id):
            return
        if state.hp <= 0:
            return
        if len(state.round_finished_users) >= len(state.participants):
            return
        await self._raid_after_round_timeout(state, channel)

    async def _raid_refresh_hub(self, state: RaidBattleState) -> None:
        if not state.hub_message:
            return
        try:
            # Ne pas repasser `view=` : sinon discord.py peut réinitialiser le délai interne du View à chaque edit.
            await state.hub_message.edit(embed=self._raid_hub_embed(state))
        except Exception:
            pass

    async def _raid_announce_hit(
        self,
        channel: discord.TextChannel,
        state: RaidBattleState,
        *,
        user_name: str,
        damage: int,
        hp_after: int,
        is_finishing_blow: bool,
    ) -> None:
        """Message public (réponse au hub) pour que chaque coup soit visible dans le salon."""
        lg = state.lang
        if not state.hub_message:
            try:
                if is_finishing_blow:
                    await channel.send(
                        _cg(lg, "hit_finisher_short", name=user_name, dmg=damage),
                    )
                else:
                    pct = _raid_hp_pct(hp_after, state.max_hp)
                    await channel.send(
                        _cg(
                            lg,
                            "hit_normal_short",
                            name=user_name,
                            dmg=damage,
                            hp=hp_after,
                            pct=pct,
                        ),
                    )
            except Exception:
                pass
            return
        max_hp = state.max_hp
        pct = _raid_hp_pct(hp_after, max_hp)
        if is_finishing_blow:
            text = _cg(
                lg,
                "hit_finisher",
                name=user_name,
                dmg=damage,
                maxhp=max_hp,
            )
        elif pct >= 70:
            text = _cg(
                lg,
                "hit_high",
                name=user_name,
                dmg=damage,
                hp=hp_after,
                pct=pct,
            )
        elif pct >= 40:
            text = _cg(
                lg,
                "hit_mid",
                name=user_name,
                dmg=damage,
                hp=hp_after,
                pct=pct,
            )
        else:
            text = _cg(
                lg,
                "hit_low",
                name=user_name,
                dmg=damage,
                hp=hp_after,
                pct=pct,
            )
        try:
            await state.hub_message.reply(content=text, mention_author=False)
        except Exception:
            try:
                await channel.send(content=text)
            except Exception:
                pass

    async def _raid_after_join(self, guild_id: int, channel: discord.TextChannel, join_view: RaidJoinView) -> None:
        if getattr(join_view, "_raid_after_join_done", False):
            return
        join_view._raid_after_join_done = True

        joined = set(join_view.joined)
        lg = i18n.guild_lang(channel.guild) if channel.guild else "fr"
        if not joined:
            await channel.send(_cg(lg, "raid_cancel_no_players"))
            _active_raids.pop(guild_id, None)
            return

        n = len(joined)
        max_hp = _raid_max_hp_for_players(n)
        player_modes = {uid: join_view.mode_by_user.get(uid, RAID_MODE_DEFAULT) for uid in joined}
        try:
            if getattr(join_view, "promo_message", None):
                await join_view.promo_message.delete()
        except Exception:
            pass
        try:
            if getattr(join_view, "message", None):
                await join_view.message.delete()
        except Exception:
            pass
        state = RaidBattleState(
            guild_id=guild_id,
            channel_id=channel.id,
            hp=max_hp,
            max_hp=max_hp,
            round_n=1,
            max_rounds=RAID_MAX_ROUNDS,
            participants=set(joined),
            player_modes=player_modes,
            raid_start_ts=monotonic(),
            lang=lg,
        )
        await channel.send(
            _cg(
                lg,
                "raid_start_body",
                n=n,
                hp=max_hp,
                per=RAID_HP_PER_PLAYER,
                maxr=RAID_MAX_ROUNDS,
                secs=int(RAID_ROUND_SECONDS),
            )
        )
        await self._raid_open_round(channel, state)

    async def _raid_open_round(self, channel: discord.TextChannel, state: RaidBattleState) -> None:
        if state.hp <= 0:
            await self._raid_conclude_victory(channel, state, extra_intro="")
            return
        await self._raid_cancel_round_timer_async(state)
        state.answered_this_round.clear()
        state.round_finished_users.clear()
        state.round_early_scheduled = False
        state.open_challenge_users.clear()
        state.round_start_ts = monotonic()
        hub = RaidRoundHubView(self, state)
        emb = self._raid_hub_embed(state)
        msg = await channel.send(embed=emb, view=hub)
        hub.message = msg
        state.hub_message = msg
        state.hub_view = hub
        state.round_timer_generation += 1
        gen = state.round_timer_generation
        state.round_timer_task = asyncio.create_task(
            self._raid_round_timer_worker(state, channel, gen)
        )

    async def _raid_maybe_finish_round_early(self, state: RaidBattleState, hub: RaidRoundHubView) -> None:
        """Si tous les inscrits ont fini leur défi (bonne réponse, faux, ou temps écoulé), enchaîne la manche."""
        ch = self.bot.get_channel(state.channel_id)
        if not isinstance(ch, discord.TextChannel):
            return
        async with state.lock:
            if state.hp <= 0:
                return
            if len(state.round_finished_users) < len(state.participants):
                return
            if state.round_early_scheduled:
                return
            state.round_early_scheduled = True
        await self._raid_complete_round_early(state, ch, hub)

    async def _raid_register_hit(
        self,
        user: discord.Member | discord.User,
        state: RaidBattleState,
        damage: int,
        dt_ms: int,
        hub: RaidRoundHubView,
        raid_mode: str,
    ) -> bool:
        uid = user.id
        name = user.display_name if hasattr(user, "display_name") else str(user)

        ch = self.bot.get_channel(state.channel_id)
        if not isinstance(ch, discord.TextChannel):
            return False

        async with state.lock:
            if state.hp <= 0:
                return False
            state.hp = max(0, state.hp - damage)
            state.damage_by_user[uid] = state.damage_by_user.get(uid, 0) + damage
            state.hits_by_user[uid] = state.hits_by_user.get(uid, 0) + 1
            prev = state.best_time_ms.get(uid)
            if prev is None or dt_ms < prev:
                state.best_time_ms[uid] = dt_ms
            state.answered_this_round.add(uid)
            state.round_finished_users.add(uid)
            state.open_challenge_users.discard(uid)
            line = _cg(
                state.lang,
                "log_hit",
                name=name,
                dmg=damage,
                ms=dt_ms,
                hp=state.hp,
            )
            state.log_lines = state.log_lines[-14:] + [line]

        await self._raid_refresh_hub(state)
        await self._raid_announce_hit(
            ch,
            state,
            user_name=name,
            damage=damage,
            hp_after=state.hp,
            is_finishing_blow=(state.hp <= 0),
        )

        if state.hp <= 0:
            state.raid_finished = True
            state.final_blow = (uid, raid_mode if raid_mode in RAID_DAMAGE_BY_MODE else RAID_MODE_DEFAULT)
            await self._raid_cancel_round_timer_async(state)
            hub.ended = True
            hub.stop()
            try:
                if state.hub_message:
                    await state.hub_message.edit(
                        content=_cg(state.lang, "hub_boss_dead"),
                        embed=self._raid_hub_embed(state),
                        view=None,
                    )
            except Exception:
                pass
            mode_lbl = _raid_mode_label(
                state.final_blow[1],
                i18n.guild_lang(ch.guild) if ch and ch.guild else "fr",
            )
            fin_xp = RAID_XP_FINISHER_BY_MODE.get(state.final_blow[1], 0)
            _lg = state.lang
            await self._raid_conclude_victory(
                ch,
                state,
                extra_intro=_cg(_lg, "final_intro", name=name, mode=mode_lbl, xp=fin_xp),
            )
            return True

        await self._raid_maybe_finish_round_early(state, hub)
        return True

    async def _raid_run_guesswho_text(
        self,
        interaction: discord.Interaction,
        state: RaidBattleState,
        hub: RaidRoundHubView,
        uid: int,
        quiz: dict[str, Any],
        damage: int,
        raid_mode: str,
    ) -> None:
        """Attend un message dans le salon du raid (même logique que /guesswho : flou + nom tapé)."""
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            async with state.lock:
                state.open_challenge_users.discard(uid)
            return

        correct_name = str(quiz.get("correct_name") or "?")
        anime_hint = str(quiz.get("anime_hint") or "")
        started_round = state.round_n
        t0 = monotonic()

        def _check(m: discord.Message) -> bool:
            return m.author.id == uid and m.channel.id == ch.id and not m.author.bot

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=RAID_ROUND_SECONDS,
                check=_check,
            )
        except asyncio.TimeoutError:
            lg = state.lang
            async with state.lock:
                if state.round_n != started_round or uid not in state.open_challenge_users:
                    return
                state.open_challenge_users.discard(uid)
                state.round_finished_users.add(uid)
                disp = getattr(interaction.user, "display_name", None) or str(interaction.user)
                state.log_lines = state.log_lines[-14:] + [
                    _cg(lg, "log_guesswho_timeout", name=disp)
                ]
            emb = discord.Embed(
                title=_cg(lg, "timeup_title"),
                description=_cg(lg, "timeup_desc", name=correct_name),
                color=discord.Color.orange(),
            )
            try:
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            except Exception:
                pass
            await self._raid_refresh_hub(state)
            await self._raid_maybe_finish_round_early(state, hub)
            return

        try:
            await msg.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        async with state.lock:
            if state.round_n != started_round or uid not in state.open_challenge_users:
                return

        g = (msg.content or "").strip()
        qz = self.bot.get_cog("Quiz")
        ok = _raid_guesswho_name_match(g, correct_name, qz)

        if not ok:
            lg = state.lang
            async with state.lock:
                if state.round_n != started_round or uid not in state.open_challenge_users:
                    return
                state.wrong_by_user[uid] = state.wrong_by_user.get(uid, 0) + 1
                state.open_challenge_users.discard(uid)
                state.round_finished_users.add(uid)
                disp = getattr(interaction.user, "display_name", None) or str(interaction.user)
                state.log_lines = state.log_lines[-14:] + [
                    _cg(lg, "log_guesswho_fail", name=disp)
                ]
            emb = discord.Embed(
                title=_cg(lg, "wrong_title"),
                description=_cg(lg, "wrong_desc", name=correct_name),
                color=discord.Color.dark_red(),
            )
            try:
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            except Exception:
                pass
            await self._raid_refresh_hub(state)
            await self._raid_maybe_finish_round_early(state, hub)
            return

        async with state.lock:
            if state.round_n != started_round or uid not in state.open_challenge_users:
                return

        dt_ms = int((monotonic() - t0) * 1000)
        applied = await self._raid_register_hit(
            interaction.user,
            state,
            damage,
            dt_ms,
            hub,
            raid_mode,
        )
        lg = state.lang
        lines: list[str] = [f"**{correct_name}**"]
        if anime_hint and anime_hint != "—":
            lines.append(_cg(lg, "hint_anime_line", hint=anime_hint))
        lines.append(_cg(lg, "success_dmg", dmg=damage, ms=dt_ms))
        desc = "\n".join(lines)
        try:
            if not applied:
                emb = discord.Embed(
                    title=_cg(lg, "already_dead_title"),
                    description=_cg(lg, "already_dead_desc"),
                    color=discord.Color.gold(),
                )
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            else:
                emb = discord.Embed(
                    title=_cg(lg, "good_title"),
                    description=desc,
                    color=discord.Color.green(),
                )
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
        except Exception:
            pass

    async def _raid_run_animequiz_text(
        self,
        interaction: discord.Interaction,
        state: RaidBattleState,
        hub: RaidRoundHubView,
        uid: int,
        quiz: dict[str, Any],
        damage: int,
        raid_mode: str,
    ) -> None:
        """Comme /animequiz (hard) : titre dans le salon, message supprimé, TitleMatcher — une tentative."""
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            async with state.lock:
                state.open_challenge_users.discard(uid)
            return

        media = quiz.get("media") or {}
        titles = _raid_titles_set_from_media(media)
        romaji = (media.get("title") or {}).get("romaji") or "?"
        started_round = state.round_n
        t0 = monotonic()

        def _check(m: discord.Message) -> bool:
            return m.author.id == uid and m.channel.id == ch.id and not m.author.bot

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=RAID_ROUND_SECONDS,
                check=_check,
            )
        except asyncio.TimeoutError:
            lg = state.lang
            async with state.lock:
                if state.round_n != started_round or uid not in state.open_challenge_users:
                    return
                state.open_challenge_users.discard(uid)
                state.round_finished_users.add(uid)
                disp = getattr(interaction.user, "display_name", None) or str(interaction.user)
                state.log_lines = state.log_lines[-14:] + [
                    _cg(lg, "log_aq_timeout", name=disp)
                ]
            emb = discord.Embed(
                title=_cg(lg, "timeup_title"),
                description=_cg(lg, "timeup_desc", name=romaji),
                color=discord.Color.orange(),
            )
            try:
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            except Exception:
                pass
            await self._raid_refresh_hub(state)
            await self._raid_maybe_finish_round_early(state, hub)
            return

        try:
            await msg.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        async with state.lock:
            if state.round_n != started_round or uid not in state.open_challenge_users:
                return

        g_raw = (msg.content or "").strip()
        if g_raw.lower() in _RAID_JSP_WORDS:
            lg = state.lang
            async with state.lock:
                if state.round_n != started_round or uid not in state.open_challenge_users:
                    return
                state.open_challenge_users.discard(uid)
                state.round_finished_users.add(uid)
                disp = getattr(interaction.user, "display_name", None) or str(interaction.user)
                state.log_lines = state.log_lines[-14:] + [
                    _cg(lg, "log_aq_pass", name=disp)
                ]
            emb = discord.Embed(
                title=_cg(lg, "pass_title"),
                description=_cg(lg, "timeup_desc", name=romaji),
                color=discord.Color.orange(),
            )
            try:
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            except Exception:
                pass
            await self._raid_refresh_hub(state)
            await self._raid_maybe_finish_round_early(state, hub)
            return

        qz = self.bot.get_cog("Quiz")
        ok = False
        if qz and titles:
            ok = bool(qz.title_matcher.find_matches(g_raw, titles))  # type: ignore[attr-defined]
        if not ok and titles:
            gl = normalize(g_raw)
            for t in titles:
                if normalize(t) == gl:
                    ok = True
                    break

        if not ok:
            lg = state.lang
            async with state.lock:
                if state.round_n != started_round or uid not in state.open_challenge_users:
                    return
                state.wrong_by_user[uid] = state.wrong_by_user.get(uid, 0) + 1
                state.open_challenge_users.discard(uid)
                state.round_finished_users.add(uid)
                disp = getattr(interaction.user, "display_name", None) or str(interaction.user)
                state.log_lines = state.log_lines[-14:] + [
                    _cg(lg, "log_aq_fail", name=disp)
                ]
            emb = discord.Embed(
                title=_cg(lg, "wrong_title_anime"),
                description=_cg(lg, "timeup_desc", name=romaji),
                color=discord.Color.dark_red(),
            )
            try:
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            except Exception:
                pass
            await self._raid_refresh_hub(state)
            await self._raid_maybe_finish_round_early(state, hub)
            return

        async with state.lock:
            if state.round_n != started_round or uid not in state.open_challenge_users:
                return

        dt_ms = int((monotonic() - t0) * 1000)
        applied = await self._raid_register_hit(
            interaction.user,
            state,
            damage,
            dt_ms,
            hub,
            raid_mode,
        )
        lg = state.lang
        desc = "\n".join(
            [f"**{romaji}**", _cg(lg, "success_dmg", dmg=damage, ms=dt_ms)]
        )
        try:
            if not applied:
                emb = discord.Embed(
                    title=_cg(lg, "already_dead_title"),
                    description=_cg(lg, "already_dead_desc"),
                    color=discord.Color.gold(),
                )
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            else:
                emb = discord.Embed(
                    title=_cg(lg, "good_title"),
                    description=desc,
                    color=discord.Color.green(),
                )
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
        except Exception:
            pass

    async def _raid_complete_round_early(
        self,
        state: RaidBattleState,
        channel: discord.TextChannel,
        hub: RaidRoundHubView,
    ) -> None:
        """Tous les inscrits ont contribué cette manche : enchaîne sans attendre le timer."""
        if not _active_raids.get(state.guild_id):
            return
        if state.hp <= 0:
            return
        await self._raid_cancel_round_timer_async(state)
        hub.ended = True
        hub.stop()
        lg = state.lang
        try:
            if state.hub_message:
                await state.hub_message.edit(
                    content=_cg(lg, "round_all_answered"),
                    embed=None,
                    view=None,
                )
        except Exception:
            pass
        await channel.send(
            _cg(lg, "round_early_msg", n=state.round_n, hp=state.hp)
        )
        if state.round_n >= state.max_rounds:
            await self._raid_force_finish(channel, state)
            return
        state.round_n += 1
        await self._raid_open_round(channel, state)

    async def _raid_after_round_timeout(self, state: RaidBattleState, channel: discord.TextChannel) -> None:
        if not _active_raids.get(state.guild_id):
            return
        if state.hp <= 0:
            return
        state.round_timer_task = None
        hv = state.hub_view
        if hv is not None and not getattr(hv, "ended", True):
            hv.ended = True
            for c in hv.children:
                if isinstance(c, Button):
                    c.disabled = True
            try:
                if state.hub_message:
                    await state.hub_message.edit(embed=self._raid_hub_embed(state), view=hv)
            except Exception:
                pass
            try:
                hv.stop()
            except Exception:
                pass
        await channel.send(
            _cg(state.lang, "round_timeout_msg", n=state.round_n, hp=state.hp)
        )
        LOG.info(
            "raid: timeout manche %s/%s (guild %s)",
            state.round_n,
            state.max_rounds,
            state.guild_id,
        )
        if state.round_n >= state.max_rounds:
            await self._raid_force_finish(channel, state)
            return
        state.round_n += 1
        await self._raid_open_round(channel, state)

    async def _raid_force_finish(self, channel: discord.TextChannel, state: RaidBattleState) -> None:
        await self._raid_cancel_round_timer_async(state)
        extra = []
        lg = state.lang
        if state.hp > 0:
            extra.append(_cg(lg, "force_finish", hp=state.hp))
            state.hp = 0
        await self._raid_conclude_victory(channel, state, extra_intro="\n".join(extra))

    async def _raid_conclude_victory(
        self,
        channel: discord.TextChannel,
        state: RaidBattleState,
        *,
        extra_intro: str = "",
    ) -> None:
        state.raid_finished = True
        await self._raid_cancel_round_timer_async(state)
        guild_id = state.guild_id
        participants = list(state.participants)
        total_dmg = sum(state.damage_by_user.values())

        mvp_uid: Optional[int] = None
        if participants:
            mvp_uid = max(participants, key=lambda u: state.damage_by_user.get(u, 0))

        fastest_uid: Optional[int] = None
        if state.best_time_ms:
            fastest_uid = min(state.best_time_ms, key=lambda u: state.best_time_ms[u])

        fin_uid: Optional[int] = None
        fin_mode: Optional[str] = None
        if state.final_blow:
            fin_uid, fin_mode = state.final_blow[0], state.final_blow[1]

        elapsed = int(monotonic() - state.raid_start_ts) if state.raid_start_ts else 0
        emin, esec = divmod(max(0, elapsed), 60)
        dur_str = f"{emin}m {esec}s" if emin else f"{esec}s"

        lg = state.lang
        summary_parts: list[str] = []
        if extra_intro:
            summary_parts.append(extra_intro.strip())
        summary_parts.append(
            _cg(
                lg,
                "victory_summary",
                np=len(participants),
                nr=state.round_n,
                dur=dur_str,
                td=total_dmg,
                maxhp=state.max_hp,
            )
        )
        lines = ["\n".join(summary_parts), "", _cg(lg, "victory_xp_header")]

        xp_lines: list[str] = []
        for uid in participants:
            share = (state.damage_by_user.get(uid, 0) / total_dmg) if total_dmg > 0 else 0.0
            xp = RAID_XP_BASE_EACH + int(RAID_XP_DAMAGE_POOL * share)
            if uid == mvp_uid and mvp_uid is not None:
                xp += RAID_XP_MVP_BONUS
            if uid == fastest_uid and fastest_uid is not None:
                xp += RAID_XP_FASTEST_BONUS
            fin_bonus = 0
            if fin_uid is not None and uid == fin_uid and fin_mode:
                fin_bonus = int(RAID_XP_FINISHER_BY_MODE.get(fin_mode, 0))
                xp += fin_bonus
            try:
                await core.add_xp(self.bot, channel, uid, xp, announce=False)
            except Exception:
                pass
            hits = state.hits_by_user.get(uid, 0)
            if hits:
                core.add_mini_score(uid, "bossraid", hits)
            uname = "?"
            m = channel.guild.get_member(uid) if channel.guild else None
            if m:
                uname = m.display_name
            badges = []
            if uid == mvp_uid:
                badges.append(_cg(lg, "badge_mvp"))
            if uid == fastest_uid:
                badges.append(_cg(lg, "badge_fast"))
            if fin_uid is not None and uid == fin_uid:
                badges.append(_cg(lg, "badge_fin", xp=fin_bonus))
            b = f" ({', '.join(badges)})" if badges else ""
            xp_lines.append(
                _cg(
                    lg,
                    "xp_line",
                    name=uname,
                    xp=xp,
                    badges=b,
                    dmg=state.damage_by_user.get(uid, 0),
                )
            )

        emb = discord.Embed(
            title=_cg(lg, "victory_title"),
            description="\n".join(lines + ["", "\n".join(xp_lines)]),
            color=discord.Color.gold(),
        )
        ft: list[str] = []
        if mvp_uid and channel.guild:
            mv = channel.guild.get_member(mvp_uid)
            if mv:
                ft.append(_cg(lg, "footer_mvp", name=mv.display_name))
        if fastest_uid is not None and fastest_uid in state.best_time_ms:
            fu = channel.guild.get_member(fastest_uid) if channel.guild else None
            nm = fu.display_name if fu else "?"
            ft.append(
                _cg(lg, "footer_fast", name=nm, ms=state.best_time_ms[fastest_uid])
            )
        if fin_uid is not None and fin_mode and channel.guild:
            fm = channel.guild.get_member(fin_uid)
            if fm:
                ft.append(
                    _cg(
                        lg,
                        "footer_fin",
                        name=fm.display_name,
                        xp=RAID_XP_FINISHER_BY_MODE.get(fin_mode, 0),
                    )
                )
        if ft:
            emb.set_footer(text=" · ".join(ft))
        try:
            await channel.send(embed=emb)
        except Exception:
            pass

        _active_raids.pop(guild_id, None)

    async def _schedule_raid_join_phase_end(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        join_view: RaidJoinView,
    ) -> None:
        """Fin d’inscription après **exactement** RAID_JOIN_SECONDS (horloge fixe au lancement)."""
        try:
            await asyncio.sleep(RAID_JOIN_SECONDS)
        except asyncio.CancelledError:
            return
        if getattr(join_view, "_raid_after_join_done", False):
            return
        try:
            join_view.stop()
        except Exception:
            pass
        await self._raid_after_join(guild.id, channel, join_view)

    async def _raid_abort(self, channel: discord.TextChannel, guild_id: int, reason: str) -> None:
        await channel.send(reason)
        _active_raids.pop(guild_id, None)

    async def _start_boss_raid(self, guild: discord.Guild, channel: discord.TextChannel, week_key: str) -> None:
        lock = await _raid_spawn_lock_for(guild.id)
        async with lock:
            if _active_raids.get(guild.id):
                return
            _active_raids[guild.id] = True
            try:
                with core.DATA_JSON_LOCK:
                    cfg = _load_raid_cfg()
                    gk = str(guild.id)
                    if gk in cfg:
                        cfg[gk]["raid_started_for_week"] = week_key
                        _save_raid_cfg(cfg)

                _lg = i18n.guild_lang(guild)
                promo = await channel.send(
                    _cg(
                        _lg,
                        "promo",
                        join=int(RAID_JOIN_SECONDS),
                        maxr=RAID_MAX_ROUNDS,
                        per_player=RAID_HP_PER_PLAYER,
                    )
                )
                join_view = RaidJoinView(self, guild.id, channel.id)
                join_view.promo_message = promo
                msg = await channel.send(
                    embed=discord.Embed(
                        title=_cg(_lg, "signup_title"),
                        description=_cg(_lg, "signup_desc"),
                        color=discord.Color.red(),
                    ),
                    view=join_view,
                )
                join_view.message = msg
                join_view._raid_join_timer_task = asyncio.create_task(
                    self._schedule_raid_join_phase_end(guild, channel, join_view)
                )
            except Exception:
                _active_raids.pop(guild.id, None)
                raise

    @tasks.loop(minutes=1.0)
    async def raid_scheduler(self) -> None:
        cfg = _load_raid_cfg()
        now = datetime.now(core.TIMEZONE)
        for gid_str, c in list(cfg.items()):
            if not isinstance(c, dict):
                continue
            if not _raid_cfg_enabled(c):
                continue
            try:
                gid = int(gid_str)
            except ValueError:
                continue
            ch_id = c.get("channel_id")
            if not ch_id:
                LOG.warning(
                    "raid scheduler: lancement auto activé mais **aucun salon** (guild_id=%s) — "
                    "ouvre /raidconfig et choisis un salon.",
                    gid_str,
                )
                continue
            # Ne pas utiliser bot.get_channel seul : il peut résoudre un salon d’un **autre** serveur
            # (ID unique global). Les alertes partaient alors ailleurs alors que alert_sent_* était
            # enregistré sous la clé JSON du serveur de test — d’où « skip » sans message visible ici.
            guild_obj = self.bot.get_guild(gid)
            if guild_obj is None:
                LOG.warning(
                    "raid scheduler: le bot n’est pas dans la guilde %s — entrée ignorée.",
                    gid_str,
                )
                continue
            raw_ch = guild_obj.get_channel(int(ch_id))
            if raw_ch is None:
                try:
                    raw_ch = await guild_obj.fetch_channel(int(ch_id))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    raw_ch = None
            if raw_ch is None:
                foreign = self.bot.get_channel(int(ch_id))
                if foreign is not None and getattr(foreign, "guild", None) and foreign.guild.id != gid:
                    cgk = f"{gid_str}:{ch_id}:{foreign.guild.id}"
                    if cgk not in self._raid_cross_guild_logged:
                        self._raid_cross_guild_logged.add(cgk)
                        if len(self._raid_cross_guild_logged) > 500:
                            self._raid_cross_guild_logged.clear()
                        LOG.error(
                            "raid scheduler: le salon %s est sur le serveur **%s**, pas **%s**. "
                            "Avec l’ancienne logique, l’alerte partait sur l’autre serveur alors que "
                            "« déjà envoyé » était enregistré pour le serveur de test — d’où aucun message ici. "
                            "Refais **`/raidconfig`** et choisis un salon **de ce serveur**.",
                            ch_id,
                            foreign.guild.id,
                            gid_str,
                        )
                        with core.DATA_JSON_LOCK:
                            cfg_clr = _load_raid_cfg()
                            ent = cfg_clr.get(gid_str)
                            if isinstance(ent, dict):
                                ent.pop("alert_sent_for_week", None)
                                ent.pop("alert_sent_message_id", None)
                                cfg_clr[gid_str] = ent
                                _save_raid_cfg(cfg_clr)
                else:
                    LOG.warning(
                        "raid scheduler: salon %s introuvable **dans** la guilde %s — "
                        "refais /raidconfig avec un salon de ce serveur (ou salon supprimé).",
                        ch_id,
                        gid_str,
                    )
                continue
            if not isinstance(raw_ch, discord.TextChannel):
                LOG.warning(
                    "raid scheduler: salon %s n’est pas un salon texte (guild_id=%s).",
                    ch_id,
                    gid_str,
                )
                continue
            channel = raw_ch
            guild = channel.guild
            if guild.id != gid:
                LOG.error(
                    "raid scheduler: incohérence interne — guild.id=%s attendu=%s",
                    guild.id,
                    gid,
                )
                continue
            try:
                weekday = int(c.get("weekday", 5))
                hour = int(c.get("hour", 20))
                minute = int(c.get("minute", 0))
            except (TypeError, ValueError):
                LOG.warning("raid scheduler: jour/heure/minute invalides (guild_id=%s)", gid_str)
                continue
            raid_at = _resolve_scheduled_raid_for_loop(now, weekday, hour, minute)
            wkey = _week_key(raid_at)
            alert_at = raid_at - timedelta(hours=1)
            sent_w = str(c.get("alert_sent_for_week") or "").strip()
            started_w = str(c.get("raid_started_for_week") or "").strip()

            if sent_w != wkey and alert_at <= now < raid_at:
                try:
                    _alert = _cg(i18n.guild_lang(guild), "alert_1h")
                    msg = await channel.send(
                        _alert,
                        allowed_mentions=discord.AllowedMentions(everyone=True),
                    )
                except Exception as e:
                    LOG.warning(
                        "raid alert 1h: échec envoi serveur=%r (%s) salon=%s semaine=%s — %s",
                        guild.name,
                        gid,
                        ch_id,
                        wkey,
                        e,
                    )
                else:
                    link = f"https://discord.com/channels/{guild.id}/{channel.id}/{msg.id}"
                    LOG.info(
                        "raid alert 1h: envoyé serveur=%r (%s) salon=%s semaine=%s créneau=%s "
                        "message_id=%s lien=%s",
                        guild.name,
                        gid,
                        ch_id,
                        wkey,
                        raid_at.isoformat(),
                        msg.id,
                        link,
                    )
                    with core.DATA_JSON_LOCK:
                        cfg2 = _load_raid_cfg()
                        if gid_str in cfg2:
                            cfg2[gid_str]["alert_sent_for_week"] = wkey
                            cfg2[gid_str]["alert_sent_message_id"] = int(msg.id)
                        _save_raid_cfg(cfg2)
            elif alert_at <= now < raid_at and sent_w == wkey:
                sk = f"{gid_str}:{wkey}"
                if sk not in self._raid_alert_skip_logged:
                    mid = c.get("alert_sent_message_id")
                    link = (
                        f"https://discord.com/channels/{gid}/{ch_id}/{int(mid)}"
                        if mid is not None
                        else "(inconnu — pas d’ID enregistré pour cette semaine)"
                    )
                    LOG.info(
                        "raid alert 1h: skip (déjà enregistré pour %s) guild=%s — pas de nouvel envoi. "
                        "Dernier message d’alerte enregistré : message_id=%s lien=%s "
                        "(si tu ne vois rien dans le salon : vérifie le salon `channel_id` dans data/boss_raid.json, "
                        "les mentions @here, ou que le message n’a pas été supprimé).",
                        wkey,
                        gid,
                        mid,
                        link,
                    )
                    self._raid_alert_skip_logged.add(sk)
                    if len(self._raid_alert_skip_logged) > 500:
                        self._raid_alert_skip_logged.clear()

            if (
                started_w != wkey
                and raid_at <= now < raid_at + timedelta(minutes=4)
                and not _active_raids.get(guild.id)
            ):
                LOG.info(
                    "raid auto: lancement boss serveur=%r (%s) semaine=%s créneau=%s (now=%s)",
                    guild.name,
                    gid,
                    wkey,
                    raid_at.isoformat(),
                    now.isoformat(),
                )
                try:
                    await self._start_boss_raid(guild, channel, wkey)
                except Exception as e:
                    LOG.exception("raid auto-start: %s", e)

    @raid_scheduler.before_loop
    async def _raid_sched_before(self) -> None:
        await self.bot.wait_until_ready()

    raid = app_commands.Group(
        name="raid",
        description=ui_str("slash.raid_group"),
    )

    @raid.command(name="statut", description=ui_str("slash.raid_statut"))
    async def raid_statut_public(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                _cg(i18n.interaction_lang(interaction), "guild_only"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=_raid_status_embed(interaction.guild),
            ephemeral=True,
        )

    @app_commands.command(
        name="raidconfig",
        description=ui_str("slash.raidconfig"),
    )
    @app_commands.default_permissions(administrator=True)
    async def raid_config_unified(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                _cg(i18n.interaction_lang(interaction), "guild_only"),
                ephemeral=True,
            )
            return
        embed = _raid_config_panel_embed(interaction.guild)
        view = RaidConfigPanelView(self, interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="raidstart", description=ui_str("slash.raidstart"))
    @app_commands.default_permissions(administrator=True)
    async def raid_start(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        if not interaction.guild:
            await interaction.response.send_message(_cg(lg, "guild_only"), ephemeral=True)
            return
        if _active_raids.get(interaction.guild.id):
            await interaction.response.send_message(_cg(lg, "raid_already_running"), ephemeral=True)
            return
        target = _raid_target_channel(interaction.guild)
        if target is None:
            await interaction.response.send_message(
                _cg(lg, "raid_no_channel"),
                ephemeral=True,
            )
            return
        if not _raidstart_week_available(interaction.guild.id):
            cur = _week_key(datetime.now(core.TIMEZONE))
            await interaction.response.send_message(
                _cg(lg, "raid_limit_cmd", wk=cur),
                ephemeral=True,
            )
            return
        wk = _week_key(datetime.now(core.TIMEZONE))
        embed = discord.Embed(
            title=_cg(lg, "raid_confirm_title"),
            description=_cg(lg, "raid_confirm_desc", wk=wk, ch=target.mention),
            color=discord.Color.dark_red(),
        )
        view = RaidStartConfirmView(self, interaction.guild, target, wk, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="raidalerttest", description=ui_str("slash.raidalerttest"))
    @app_commands.default_permissions(administrator=True)
    async def raid_alert_test(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        if not interaction.guild:
            await interaction.response.send_message(_cg(lg, "guild_only"), ephemeral=True)
            return
        target = _raid_target_channel(interaction.guild)
        if target is None:
            await interaction.response.send_message(
                _cg(lg, "raid_no_channel"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await target.send(
                _cg(lg, "test_alert"),
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                _cg(lg, "test_forbidden", ch=target.mention),
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(_cg(lg, "test_err", err=e), ephemeral=True)
            return
        await interaction.followup.send(_cg(lg, "test_ok", ch=target.mention), ephemeral=True)

    # ---------- Chain quiz ----------

    @commands.hybrid_command(name="chainquiz", description=ui_str("slash.chainquiz"))
    @commands.cooldown(1, 35, commands.BucketType.user)
    async def chainquiz(self, ctx: commands.Context) -> None:
        if not await _require_slash(ctx, "chainquiz"):
            return
        uid = ctx.author.id
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "chainquiz"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            lg = i18n.ctx_lang(ctx)
            qz = self.bot.get_cog("Quiz")
            if not qz:
                await ctx.send(_cg(lg, "chain_no_quiz"))
                return

            streak = 0
            total_xp = 0
            await ctx.send(_cg(lg, "chain_intro"))

            while True:
                diff = SORT_CHAIN[min(streak, len(SORT_CHAIN) - 1)]
                diff_label = {
                    "easy": _cg(lg, "diff_easy"),
                    "medium": _cg(lg, "diff_normal"),
                    "hard": _cg(lg, "diff_hard"),
                }.get(diff, diff)
                sort_key = SORT_TO_ANILIST[diff]
                anime = await qz._fetch_random_anilist_media(sort_key, queue_ctx=ctx)  # type: ignore[attr-defined]
                if not anime:
                    await ctx.send(core.anilist_error_user_message(lg))
                    break
                titles = qz._titles_set(anime)  # type: ignore[attr-defined]
                embed = discord.Embed(
                    title=_cg(lg, "chain_round", n=streak + 1, diff=diff_label),
                    description=_cg(lg, "chain_desc", sec=20 + streak * 5),
                    color=discord.Color.gold(),
                )
                img = (anime.get("coverImage") or {}).get("extraLarge") or (anime.get("coverImage") or {}).get("large")
                if img:
                    embed.set_image(url=img)
                await ctx.send(embed=embed)
                try:
                    msg = await self.bot.wait_for(
                        "message",
                        timeout=float(20 + streak * 5),
                        check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                    )
                except asyncio.TimeoutError:
                    await ctx.send(_cg(lg, "chain_timeout", streak=streak))
                    break
                guess = (msg.content or "").strip()
                if guess.lower() in {"jsp", "pass", "skip"}:
                    await ctx.send(_cg(lg, "chain_skip", streak=streak, xp=total_xp))
                    break
                if qz.title_matcher.find_matches(guess, titles):  # type: ignore[attr-defined]
                    streak += 1
                    xp = 5 + min(streak, 8) * 2
                    total_xp += xp
                    await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp, announce=False)
                    core.add_mini_score(ctx.author.id, "chainquiz", 1)
                    self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_win")
                    self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_solo_ok")
                    await ctx.send(_cg(lg, "chain_ok", xp=xp, streak=streak))
                else:
                    rom = (anime.get("title") or {}).get("romaji") or "?"
                    await ctx.send(
                        _cg(lg, "chain_wrong", title=rom, streak=streak, xp=total_xp)
                    )
                    break

        finally:
            minigame_lock.end(uid)

    # ---------- Guess who (flou) ----------

    @commands.hybrid_command(
        name="guesswho",
        description=ui_str("slash.guesswho"),
    )
    @app_commands.describe(
        difficulte=ui_str("slash.guesswho_param_diff"),
    )
    @app_commands.choices(
        difficulte=[
            app_commands.Choice(name=ui_str("slash.choice_guesswho_easy"), value="easy"),
            app_commands.Choice(name=ui_str("slash.choice_guesswho_medium"), value="medium"),
            app_commands.Choice(name=ui_str("slash.choice_guesswho_hard"), value="hard"),
        ]
    )
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def guesswho(self, ctx: commands.Context, difficulte: str = "medium") -> None:
        if not await _require_slash(ctx, "guesswho"):
            return
        uid = ctx.author.id
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "guesswho"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            lg = i18n.ctx_lang(ctx)
            div, blur_r, timeout_sec, xp_win = GUESSWHO_MODES.get(difficulte, GUESSWHO_MODES["medium"])
            diff_label = {
                "easy": _cg(lg, "diff_easy"),
                "medium": _cg(lg, "diff_normal"),
                "hard": _cg(lg, "diff_hard"),
            }.get(difficulte, _cg(lg, "diff_normal"))

            linked = core.get_linked_username(uid)
            gw = core.build_guesswho_from_user_list(linked) if linked else None

            if gw:
                name = gw["name"]
                url = gw["image_url"]
                hint = gw["hint_anime"]
            else:
                page = random.randint(1, 100)
                query = """
                query ($page: Int) {
                  Page(page: $page, perPage: 1) {
                    characters(sort: FAVOURITES_DESC) {
                      name { full }
                      image { large }
                      media(type: ANIME) { nodes { title { romaji } } }
                    }
                  }
                }
                """
                data = await core.query_anilist_async(query, {"page": page}, queue_ctx=ctx)
                if not data or "data" not in data:
                    await ctx.send(core.anilist_error_user_message(lg))
                    return
                chars = data["data"]["Page"]["characters"]
                if not chars:
                    await ctx.send(_cg(lg, "gw_no_char"))
                    return
                char = chars[0]
                name = char["name"]["full"]
                url = (char.get("image") or {}).get("large")
                nodes = (char.get("media") or {}).get("nodes") or []
                hint = nodes[0]["title"]["romaji"] if nodes else "—"

            buf = io.BytesIO()
            if url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            raw = await resp.read()
                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                    d = max(3, int(div))
                    im = im.resize((max(32, im.width // d), max(32, im.height // d)), Image.Resampling.LANCZOS)
                    im = im.resize((im.width * d, im.height * d), Image.Resampling.NEAREST)
                    im = im.filter(ImageFilter.GaussianBlur(radius=float(blur_r)))
                    im.save(buf, format="PNG")
                    buf.seek(0)
                except Exception as e:
                    LOG.warning("guesswho blur: %s", e)
                    buf = None
            else:
                buf = None

            embed = discord.Embed(
                title=_cg(lg, "gw_title"),
                description=_cg(
                    lg,
                    "gw_desc",
                    diff=diff_label,
                    xp=xp_win,
                    sec=int(timeout_sec),
                    hint=hint,
                ),
                color=discord.Color.purple(),
            )
            if gw:
                embed.set_footer(text=_cg(lg, "gw_footer_list"))
            elif linked:
                embed.set_footer(text=_cg(lg, "gw_footer_global"))
            if buf:
                embed.set_image(url="attachment://guesswho.png")
                file = discord.File(buf, filename="guesswho.png")
                await ctx.send(embed=embed, file=file)
            else:
                await ctx.send(embed=embed)

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=timeout_sec,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                )
            except asyncio.TimeoutError:
                await ctx.send(
                    _cg(
                        lg,
                        "gw_timeout",
                        name=name,
                        diff=diff_label,
                        xp=xp_win,
                    )
                )
                return

            g = (msg.content or "").strip()
            qz = self.bot.get_cog("Quiz")
            ok = False
            if qz:
                ok = bool(qz.title_matcher.find_matches(g, {name}))  # type: ignore[attr-defined]
            if not ok:
                ok = normalize(g) == normalize(name)
            if ok:
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp_win, announce=False)
                core.add_mini_score(ctx.author.id, "guesswho", 1)
                await ctx.send(
                    _cg(lg, "gw_win", name=name, xp=xp_win, diff=diff_label)
                )
            else:
                await ctx.send(
                    _cg(lg, "gw_lose", name=name, diff=diff_label, xp=xp_win)
                )

        finally:
            minigame_lock.end(uid)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityGames(bot))
