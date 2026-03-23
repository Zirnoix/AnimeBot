# cogs/reminder_digest.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import os, json, logging, asyncio

import discord
from discord.ext import commands, tasks
from discord import app_commands

from modules import core

LOG = logging.getLogger(__name__)

COLOR_OK = discord.Color.blurple()
COLOR_WARN = discord.Color.orange()
SENT_PATH = "data/daily_sent.json"  # {user_id: "YYYY-MM-DD"} dernière date envoyée

# ---------- persistence ----------
def _load_sent() -> Dict[str, str]:
    try:
        with open(SENT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_sent(data: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(SENT_PATH), exist_ok=True)
    with open(SENT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- helpers ----------
def _now_tz() -> datetime:
    try:
        tz = getattr(core, "TIMEZONE", timezone.utc)
        return datetime.now(tz)
    except Exception:
        return datetime.now(timezone.utc)

def _today_str_tz() -> str:
    return _now_tz().strftime("%Y-%m-%d")

def _is_today_ts(ts: int) -> bool:
    try:
        dt = datetime.fromtimestamp(int(ts), tz=getattr(core, "TIMEZONE", timezone.utc))
        return dt.date() == _now_tz().date()
    except Exception:
        return False

def _format_time(ts: int) -> str:
    try:
        dt = datetime.fromtimestamp(int(ts), tz=getattr(core, "TIMEZONE", timezone.utc))
        return dt.strftime("%H:%M")
    except Exception:
        return "—"

def _fmt_list(items: List[dict], limit: int = 25) -> List[tuple[str, str]]:
    """Retourne [(name, value)] pour embed.add_field."""
    out = []
    for it in items[:limit]:
        media = it.get("media") or {}
        # cas items "perso" (get_upcoming_episodes) vs items "global" (get_airings_global)
        title_dict = media.get("title") or it.get("title") or {}
        if isinstance(title_dict, dict):
            title = title_dict.get("romaji") or title_dict.get("english") or title_dict.get("native") or "Titre inconnu"
        else:
            title = str(title_dict or "Titre inconnu")
        ep = it.get("episode") or "?"
        ts = it.get("airingAt")
        hour = _format_time(ts)
        genres = (media.get("genres") if media else (it.get("genres") or [])) or []
        emoji = core.genre_emoji(genres)
        name = f"{emoji} {title} — Épisode {ep}"
        value = f"⏰ {hour}"
        out.append((name, value))
    return out

# ---------- user settings (une seule source de vérité) ----------
def _load_settings() -> dict:
    return core.load_user_settings() or {}

def _save_settings(data: dict) -> None:
    core.save_user_settings(data or {})

def _get_user_pref(uid: int) -> dict:
    return _load_settings().get(str(uid), {})

def _set_user_pref(uid: int, **updates) -> None:
    data = _load_settings()
    u = data.get(str(uid), {})
    u.update(updates)
    data[str(uid)] = u
    _save_settings(data)

def _hhmm_valid(s: str) -> bool:
    try:
        hh, mm = s.split(":")
        h = int(hh); m = int(mm)
        return 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return False

class ReminderDigest(commands.Cog):
    """Fusion: commandes /reminder & /setalert + envoi DU récap quotidien (joli), sans doublons."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sent = _load_sent()
        self._tick_lock = asyncio.Lock()
        self.ticker.start()

    def cog_unload(self):
        try:
            self.ticker.cancel()
        except Exception:
            pass
        try:
            _save_sent(self.sent)
        except Exception:
            pass

    # ---------- commandes ----------
    @staticmethod
    def _reminder_on(state: str) -> bool:
        return (state or "").strip().lower() == "on"

    @commands.hybrid_command(name="reminder", description="Active/Désactive le récap quotidien en MP.")
    @app_commands.describe(
        state="Choisis on ou off",
        heure="Optionnel — heure du récap en MP (HH:MM). Sinon utilise /setalert ou la valeur déjà enregistrée.",
    )
    @app_commands.choices(
        state=[app_commands.Choice(name="on", value="on"), app_commands.Choice(name="off", value="off")]
    )
    async def reminder(
        self,
        ctx: commands.Context,
        state: str,
        heure: Optional[str] = None,
    ):
        on = self._reminder_on(state)
        pref_updates: Dict[str, Any] = {"reminder_on": on}
        if heure is not None and str(heure).strip():
            hh = str(heure).strip()
            if not _hhmm_valid(hh):
                return await ctx.reply("❌ Heure invalide. Exemple : `08:00`", ephemeral=True)
            pref_updates["alert_time"] = hh
        _set_user_pref(ctx.author.id, **pref_updates)
        if on:
            linked = core.get_linked_username(ctx.author.id)
            if not linked:
                em = discord.Embed(
                    title="🔔 Rappel activé — aucun compte AniList lié",
                    description=(
                        "Tu recevras un **récap global** (sorties du jour sur AniList, pas la **liste du serveur** `/airings`).\n"
                        "Pour un récap basé sur **ta liste** AniList : `/linkanilist <pseudo>`."
                    ),
                    color=COLOR_WARN
                )
            else:
                em = discord.Embed(
                    title="🔔 Rappel activé",
                    description=(
                        f"Récap **personnalisé** : épisodes à venir liés à **ton** compte AniList (**{linked}**), "
                        "pas celui du serveur."
                    ),
                    color=COLOR_OK
                )
            pref = _get_user_pref(ctx.author.id)
            hhmm = pref.get("alert_time", core.get_config().get("default_alert_time", "08:00"))
            em.add_field(name="Heure d’envoi", value=f"`{hhmm}` (fuseau du bot)", inline=False)
            await ctx.reply(embed=em, ephemeral=True)
        else:
            await ctx.reply("⏹️ Rappel **désactivé**.", ephemeral=True)

    @commands.hybrid_command(name="setalert", description="Règle l’heure du récap quotidien en MP (HH:MM).")
    async def setalert(self, ctx: commands.Context, heure: str):
        if not _hhmm_valid(heure):
            return await ctx.reply("❌ Format invalide. Exemple : `08:00`", ephemeral=True)
        _set_user_pref(ctx.author.id, alert_time=heure)
        await ctx.reply(f"⏰ Heure du rappel réglée sur **{heure}** (timezone du bot).", ephemeral=True)

    # ---------- boucle d'envoi ----------
    @tasks.loop(minutes=1)
    async def ticker(self):
        # anti-réentrance (évite chevauchement si tick prend du temps)
        if self._tick_lock.locked():
            return
        async with self._tick_lock:
            await self._do_tick()

    @ticker.before_loop
    async def before_ticker(self):
        await self.bot.wait_until_ready()

    async def _do_tick(self):
        now = _now_tz()
        hhmm_now = now.strftime("%H:%M")
        today = _today_str_tz()

        settings = _load_settings()  # {uid: {"reminder_on":bool,"alert_time":"HH:MM"}}
        if not settings:
            return

        for uid, cfg in settings.items():
            try:
                if not cfg.get("reminder_on"):
                    continue
                target_hhmm = cfg.get("alert_time") or core.get_config().get("default_alert_time", "08:00")
                if target_hhmm != hhmm_now:
                    continue

                # déjà envoyé aujourd'hui ?
                if self.sent.get(uid) == today:
                    continue

                user = self.bot.get_user(int(uid))
                if not user:
                    try:
                        user = await self.bot.fetch_user(int(uid))
                    except Exception:
                        continue
                if not user:
                    continue

                embed = await self._build_daily_embed(int(uid))
                try:
                    await user.send(embed=embed)
                    self.sent[uid] = today
                    _save_sent(self.sent)
                except discord.Forbidden:
                    LOG.warning("MP refusé par %s", uid)
                except Exception as e:
                    LOG.warning("Envoi digest à %s échoué: %s", uid, e)
            except Exception as e:
                LOG.exception("Tick pour %s échoué: %s", uid, e)

    # ---------- construction de l'embed (style daily_digest) ----------
    async def _build_daily_embed(self, uid: int) -> discord.Embed:
        now_tz = _now_tz()
        linked = core.get_linked_username(uid)

        if linked:
            # perso: on prend get_upcoming_episodes puis on filtre "aujourd'hui"
            try:
                items = core.get_upcoming_episodes(linked) or []
                today_eps = [ep for ep in items if _is_today_ts(ep.get("airingAt", 0))]
            except Exception:
                today_eps = []
            title = "🗓️ Récap des sorties d'aujourd'hui — personnel"
            descr = f"Compte lié : **{linked}**"
        else:
            # global: on prend le planning global sur 1 jour
            try:
                items = core.get_airings_global(days=1, limit=50) or []
            except Exception:
                items = []

            # homogénéiser le format attendu par _fmt_list
            today_eps = []
            for it in items:
                m = it.get("media") or {}
                tdict = m.get("title") or {}
                today_eps.append({
                    "title": {
                        "romaji": tdict.get("romaji") or tdict.get("english") or tdict.get("native")
                    },
                    "episode": it.get("episode"),
                    "airingAt": it.get("airingAt"),
                    "genres": m.get("genres") or [],
                    "media": m,
                })
            title = "🗓️ Récap des sorties d'aujourd'hui"
            descr = f"Fuseau : {now_tz.tzname()}"

        em = discord.Embed(title=title, description=descr, color=COLOR_OK)

        if not today_eps:
            em.add_field(name="Aujourd’hui", value="Rien de prévu ✅", inline=False)
            em.set_footer(text="Astuce : /monplanning · /next (mode global)")
            return em

        today_eps.sort(key=lambda e: e.get("airingAt", 0))
        for name, value in _fmt_list(today_eps, limit=25):
            em.add_field(name=name, value=value, inline=False)
        em.set_footer(text="Astuce : /monnext · /planning")
        return em

async def setup(bot: commands.Bot):
    await bot.add_cog(ReminderDigest(bot))
