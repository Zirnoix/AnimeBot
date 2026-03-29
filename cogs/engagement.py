"""
Engagement features: daily check-in (streak) + daily missions (refonte).
- /checkin
- /streak
- /mission              -> affiche la mission du jour (menu action)
- /mission reroll       -> 1 reroll par SEMAINE (lundi→dimanche)

Missions : commandes du bot, combos « commandes distinctes », événements (duel gagné, quiz, level up).
Récompenses adaptées à la difficulté (EASY/MEDIUM/HARD).
"""

from __future__ import annotations
import logging
import os
import random
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List

import discord
from discord.ext import commands
from discord import app_commands

from modules import core
from modules.mission_definitions import (
    DEFAULT_MISSION_HINT,
    MISSION_HINTS,
    mission_state_from_def,
    pick_weighted_random_mission,
)
from modules.mission_logic import mission_apply_progress

LOG = logging.getLogger(__name__)

STREAK_PATH   = "data/streaks.json"
MISSIONS_PATH = "data/missions.json"

# ----------------- helpers -----------------
def _bar(current: int, goal: int, width: int = 20) -> str:
    goal = max(1, int(goal or 1))
    cur  = max(0, min(int(current or 0), goal))
    fill = int(round(width * cur / goal))
    return "▰" * fill + "▱" * (width - fill)

def _today_str() -> str:
    return datetime.now(tz=core.TIMEZONE).strftime("%Y-%m-%d")

def _today_date() -> date:
    return datetime.now(tz=core.TIMEZONE).date()

def _yesterday_str() -> str:
    d = datetime.now(tz=core.TIMEZONE) - timedelta(days=1)
    return d.strftime("%Y-%m-%d")

def _fmt(n: int) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)

def _same_iso_week(d1: date, d2: date) -> bool:
    # même semaine ISO (année+numéro de semaine)
    return d1.isocalendar()[:2] == d2.isocalendar()[:2]

def _next_monday(d: date) -> date:
    # lundi=0 ... dimanche=6
    return d + timedelta(days=(7 - d.weekday()) % 7 or 7)

def _days_until(d: date) -> int:
    t = _today_date()
    return max(0, (d - t).days)


def _next_mission_reset_unix() -> int:
    """Unix (UTC) du prochain minuit dans le fuseau du bot — pour `<t:…:R>` (compte à rebours côté Discord)."""
    now = datetime.now(tz=core.TIMEZONE)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_midnight = start_today + timedelta(days=1)
    return int(next_midnight.timestamp())


# Barème de récompenses selon difficulté (min, max)
REWARD_TABLE = {
    "EASY":   (20, 35),
    "MEDIUM": (45, 65),
    "HARD":   (80, 120),
}
DEFAULT_REWARD_FALLBACK = 20


def _roll_reward(difficulty: str) -> int:
    lo, hi = REWARD_TABLE.get(difficulty, (DEFAULT_REWARD_FALLBACK, DEFAULT_REWARD_FALLBACK))
    return random.randint(lo, hi)


# ----------------- Cog -----------------
class Engagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.streaks: Dict[str, Dict[str, Any]] = core.load_json(STREAK_PATH, {})
        self.missions: Dict[str, Dict[str, Any]] = core.load_json(MISSIONS_PATH, {})

    # ------------- DAILY CHECK-IN / STREAK -------------
    @commands.hybrid_command(name="checkin", aliases=["daily", "login"])
    async def checkin(self, ctx: commands.Context):
        """Check-in du jour : augmente ta série (streak) et donne de l’XP."""
        uid = str(ctx.author.id)
        today = _today_str()
        yesterday = _yesterday_str()
        with core.DATA_JSON_LOCK:
            self.streaks = core.load_json(STREAK_PATH, {})
            data = self.streaks.get(uid, {"last": None, "streak": 0, "best": 0})

            if data.get("last") == today:
                already = True
            else:
                already = False
                if data.get("last") == yesterday:
                    data["streak"] = int(data.get("streak", 0)) + 1
                else:
                    data["streak"] = 1

                data["best"] = max(int(data.get("best", 0)), data["streak"])
                data["last"] = today
                self.streaks[uid] = data
                core.save_json(STREAK_PATH, self.streaks)

        if already:
            return await ctx.send("✅ Tu as **déjà** fait ton check-in aujourd’hui.")

        try:
            core.add_mini_score(int(uid), "checkin", 1)
        except Exception:
            pass

        s = data["streak"]
        if s == 1:
            xp = 10
        elif s == 2:
            xp = 15
        elif 3 <= s < 7:
            xp = 20
        else:
            xp = 30

        await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp)

        next_milestone = ((s // 7) + 1) * 7
        to_next = max(0, next_milestone - s)
        bar = _bar(next_milestone - to_next, next_milestone)

        embed = discord.Embed(
            title="📆 Check-in quotidien",
            description=(
                f"🔥 **Série actuelle :** {s} jour{'s' if s>1 else ''}\n"
                f"🏅 **Meilleur record :** {data['best']}\n"
                f"🎁 **Récompense :** +{xp} XP\n\n"
                f"Prochain palier **{next_milestone}** : {bar}  (reste **{to_next}**)"
            ),
            color=discord.Color.green(),
        )
        ft = "Reviens chaque jour pour entretenir ta série !"
        if not core.get_linked_username(ctx.author.id):
            ft += " · /linkanilist : stats AniList + récaps MP"
        embed.set_footer(text=ft[:2048])
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="streak")
    async def streak(self, ctx: commands.Context):
        """Affiche ta série quotidienne et ton record."""
        uid = str(ctx.author.id)
        with core.DATA_JSON_LOCK:
            self.streaks = core.load_json(STREAK_PATH, {})
        data = self.streaks.get(uid, {"streak": 0, "best": 0})
        s, b = int(data.get("streak", 0)), int(data.get("best", 0))
        if s <= 0:
            return await ctx.send("📭 Aucune série en cours. Utilise **/checkin** pour commencer.")
        next_milestone = ((s // 7) + 1) * 7
        to_next = max(0, next_milestone - s)
        bar = _bar(next_milestone - to_next, next_milestone)
        await ctx.send(
            f"🔥 **Série actuelle : {s}**  |  🏅 **Record : {b}**\n"
            f"Prochain palier **{next_milestone}** : {bar} (reste **{to_next}**)"
        )

    # ------------- DAILY MISSION -------------
    def _roll_new_mission_payload(
        self,
        *,
        carry_last_rr: Any,
        today: str,
        avoid_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Évite de retomber sur la même mission qu’hier (ou la mission en cours au reroll) si le tirage le permet."""
        d = pick_weighted_random_mission()
        if avoid_key:
            for _ in range(40):
                if d.key != avoid_key:
                    break
                d = pick_weighted_random_mission()
        base = mission_state_from_def(d, reward_xp=_roll_reward(d.difficulty))
        return {"date": today, "last_reroll": carry_last_rr, **base}

    def _get_or_create_today_mission(self, uid: str) -> Dict[str, Any]:
        with core.DATA_JSON_LOCK:
            self.missions = core.load_json(MISSIONS_PATH, {})
            today = _today_str()
            m = self.missions.get(uid)
            if m and m.get("date") == today:
                m.setdefault("difficulty", "EASY")
                m.setdefault("reward_xp", _roll_reward(m.get("difficulty", "EASY")))
                # important : on ne touche PAS à last_reroll ici
                if "commands" in m and isinstance(m["commands"], list):
                    m["commands"] = list(set(m["commands"]))
                if "distinct" not in m:
                    m["distinct"] = m.get("key") == "use_3_tracking"
                m.setdefault("distinct_used", [])
                self.missions[uid] = m
                return m

            prev = self.missions.get(uid) or {}
            carry_last_rr = prev.get("last_reroll")
            avoid_yesterday = prev.get("key") if isinstance(prev.get("key"), str) else None
            m = self._roll_new_mission_payload(
                carry_last_rr=carry_last_rr, today=today, avoid_key=avoid_yesterday
            )
            self.missions[uid] = m
            core.save_json(MISSIONS_PATH, self.missions)
            return m

    def _mission_bar_line(self, progress: int, goal: int) -> str:
        return f"{_bar(progress, goal)}  **{progress}/{goal}**"

    async def _after_mission_progress(
        self,
        uid: int,
        m: Dict[str, Any],
        *,
        ctx: Optional[commands.Context] = None,
    ) -> None:
        """Sauvegarde ; si objectif atteint et pas encore complétée : XP + notification."""
        uid_str = str(uid)
        goal = int(m.get("goal", 1))
        prog = int(m.get("progress", 0))
        if prog < goal:
            with core.DATA_JSON_LOCK:
                self.missions = core.load_json(MISSIONS_PATH, {})
                self.missions[uid_str] = m
                core.save_json(MISSIONS_PATH, self.missions)
            return
        if m.get("completed"):
            with core.DATA_JSON_LOCK:
                self.missions = core.load_json(MISSIONS_PATH, {})
                self.missions[uid_str] = m
                core.save_json(MISSIONS_PATH, self.missions)
            return

        m["completed"] = True
        xp = int(m.get("reward_xp", DEFAULT_REWARD_FALLBACK))
        try:
            core.add_mini_score(uid, "mission_completed", 1)
        except Exception:
            pass
        await core.add_xp(self.bot, ctx.channel if ctx else None, uid, xp)

        if ctx and ctx.channel:
            try:
                await ctx.send(f"🎯 **Mission accomplie !** +{xp} XP")
            except Exception as e:
                LOG.debug("mission notify channel failed uid=%s: %s", uid, e)
        elif core.get_mission_dm_notify(uid):
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            if user:
                try:
                    await user.send(f"🎯 **Mission accomplie !** +{xp} XP")
                except discord.Forbidden:
                    pass
                except Exception as e:
                    LOG.debug("mission notify DM failed uid=%s: %s", uid, e)

        with core.DATA_JSON_LOCK:
            self.missions = core.load_json(MISSIONS_PATH, {})
            self.missions[uid_str] = m
            core.save_json(MISSIONS_PATH, self.missions)

    async def _try_complete_mission(self, ctx: commands.Context):
        """Appelée après chaque commande réussie (listener)."""
        uid = str(ctx.author.id)
        m = self._get_or_create_today_mission(uid)
        if m.get("completed"):
            return

        cmd = (ctx.command.qualified_name if ctx.command else "") or ""
        if not mission_apply_progress(m, cmd):
            return
        await self._after_mission_progress(ctx.author.id, m, ctx=ctx)

    # ---- /mission avec menu déroulant d’action ----
    @commands.hybrid_command(name="mission", description="Ta mission du jour (afficher / reroll / MP).")
    @app_commands.describe(action="Que veux-tu faire ?")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Afficher", value="show"),
            app_commands.Choice(name="Reroll (1/sem.)", value="reroll"),
            app_commands.Choice(name="MP fin de mission : ON", value="dm_on"),
            app_commands.Choice(name="MP fin de mission : OFF", value="dm_off"),
        ]
    )
    async def mission(self, ctx: commands.Context, action: Optional[str] = None):
        """Affiche ta mission du jour. `/mission` ou `/mission action: Reroll (1/sem.)`."""
        # normalise si Choice
        if isinstance(action, app_commands.Choice):
            action = action.value

        al = (action or "show")
        if isinstance(al, str):
            al = al.lower().strip()
        else:
            al = "show"

        if al in ("dm_on", "mp_on", "notif_on"):
            core.set_mission_dm_notify(ctx.author.id, True)
            msg = (
                "✅ Tu recevras un **MP** quand une mission se termine **hors salon** "
                "(quiz, duel, level up, etc.). Les missions validées par une commande restent annoncées dans le salon."
            )
            if ctx.interaction:
                if not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message(msg, ephemeral=True)
                else:
                    await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg)
            return

        if al in ("dm_off", "mp_off", "notif_off"):
            core.set_mission_dm_notify(ctx.author.id, False)
            msg = (
                "✅ **MP désactivés** pour les missions terminées hors salon. "
                "Tu gardes l’XP ; les missions complétées par une commande s’affichent toujours dans le salon."
            )
            if ctx.interaction:
                if not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message(msg, ephemeral=True)
                else:
                    await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg)
            return

        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=False)

        uid = str(ctx.author.id)
        m = self._get_or_create_today_mission(uid)
        just_rerolled = False

        # -------- reroll weekly --------
        if action and action.lower() in {"reroll", "re", "r"}:
            today = _today_date()
            last_rr_iso = m.get("last_reroll")
            last_rr = None
            if last_rr_iso:
                try:
                    last_rr = date.fromisoformat(last_rr_iso)
                except Exception:
                    last_rr = None

            # bloquer même semaine ISO
            if last_rr and _same_iso_week(last_rr, today):
                nxt = _next_monday(last_rr)
                wait_days = _days_until(nxt)
                msg = (
                    f"♻️ Tu as **déjà utilisé** ton reroll cette semaine.\n"
                    f"🔒 Prochain reroll dispo **lundi {nxt.strftime('%d/%m')}** (dans **{wait_days}** jour{'s' if wait_days>1 else ''})."
                )
                send = ctx.send if not ctx.interaction else ctx.interaction.followup.send
                return await send(msg)

            # autorisé → regénère (évite de retomber sur la même mission qu’avant le reroll)
            old_key = str(m.get("key") or "")
            rolled = self._roll_new_mission_payload(
                carry_last_rr=m.get("last_reroll"),
                today=_today_str(),
                avoid_key=old_key or None,
            )
            m.update({**rolled, "last_reroll": today.isoformat()})
            with core.DATA_JSON_LOCK:
                self.missions = core.load_json(MISSIONS_PATH, {})
                self.missions[uid] = m
                core.save_json(MISSIONS_PATH, self.missions)
            just_rerolled = True

        # -------- affichage --------
        progress = int(m.get("progress", 0))
        goal     = int(m.get("goal", 1))
        status   = "✅ **Terminée**" if m.get("completed") else "⏳ En cours"
        diff     = m.get("difficulty", "EASY")
        xp       = int(m.get("reward_xp", DEFAULT_REWARD_FALLBACK))
        diff_badge = {"EASY":"🟢 Facile", "MEDIUM":"🟡 Moyen", "HARD":"🔴 Difficile"}.get(diff, diff)
        color = {"EASY": discord.Color.green(), "MEDIUM": discord.Color.gold(), "HARD": discord.Color.red()}.get(
            diff, discord.Color.blurple()
        )
        mkey = str(m.get("key", ""))
        hint = MISSION_HINTS.get(mkey, DEFAULT_MISSION_HINT)

        # Pied d’embed : rappel reroll uniquement si déjà utilisé cette semaine (sinon la commande suffit)
        rr_line = ""
        last_rr_iso = m.get("last_reroll")
        if last_rr_iso:
            try:
                last_rr = date.fromisoformat(last_rr_iso)
                if _same_iso_week(last_rr, _today_date()):
                    nxt = _next_monday(last_rr)
                    wait_days = _days_until(nxt)
                    rr_line = f"🔒 Reroll déjà pris — prochain **lundi {nxt.strftime('%d/%m')}** (dans **{wait_days}** j.)"
            except Exception:
                pass

        embed = discord.Embed(
            title="📋 Mission du jour",
            description=(
                f"**{m['label']}**\n\n"
                f"{self._mission_bar_line(progress, goal)}\n"
                f"📌 {status}"
            ),
            color=color,
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Enjeu", value=f"**+{_fmt(xp)} XP** · {diff_badge}", inline=False)
        embed.add_field(name="Comment faire", value=hint, inline=False)
        ts = _next_mission_reset_unix()
        embed.add_field(
            name="⏱️ Prochaine mission",
            value=f"Nouvelle mission <t:{ts}:R> (minuit, fuseau du bot).",
            inline=False,
        )
        if m.get("completed"):
            embed.add_field(
                name="Demain",
                value="Pense à **`/checkin`** pour la série !",
                inline=False,
            )
        else:
            embed.add_field(
                name="Astuce",
                value="**`/checkin`** augmente ta série de jours ; **/quiz** et **/minijeux** comptent souvent pour d’autres défis.",
                inline=False,
            )
        foot: List[str] = []
        if just_rerolled:
            foot.append("Nouvelle mission tirée (reroll utilisé pour la semaine).")
        if rr_line:
            foot.append(rr_line)
        embed.set_footer(text=" · ".join(foot) if foot else "Une mission différente chaque jour")
        send = ctx.send if not ctx.interaction else ctx.interaction.followup.send
        await send(embed=embed)

    # ------------- listeners de progression -------------
    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if not ctx or not ctx.command or ctx.author.bot:
            return
        try:
            await self._try_complete_mission(ctx)
        except Exception as e:
            LOG.debug("mission on_command_completion: %s", e, exc_info=True)

    # Hook générique pour que d’autres cogs poussent une progression:
    #   self.bot.dispatch("mission_progress", user_id, "_custom:duel_win")
    @commands.Cog.listener()
    async def on_mission_progress(self, user_id: int, key: str):
        try:
            await self._custom_progress(user_id, key)
        except Exception as e:
            LOG.debug("mission on_mission_progress: %s", e, exc_info=True)

    # Si ton système XP dispatch un level up:
    #   self.bot.dispatch("level_up", user_id, new_level)
    @commands.Cog.listener()
    async def on_level_up(self, user_id: int, new_level: int):
        try:
            await self._custom_progress(user_id, "_custom:level_up")
        except Exception as e:
            LOG.debug("mission on_level_up: %s", e, exc_info=True)

    async def _custom_progress(self, uid: int, key: str):
        uid_str = str(uid)
        m = self._get_or_create_today_mission(uid_str)
        if m.get("completed") or key not in set(m.get("commands", [])):
            return
        if not mission_apply_progress(m, key):
            return
        await self._after_mission_progress(uid, m, ctx=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Engagement(bot))
