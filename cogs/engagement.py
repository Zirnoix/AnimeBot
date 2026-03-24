"""
Engagement features: daily check-in (streak) + daily missions (refonte).
- /checkin
- /streak
- /mission              -> affiche la mission du jour (menu action)
- /mission reroll       -> 1 reroll par SEMAINE (lundi→dimanche)

Missions :
- Utiliser des commandes AniList (/next, /planning, /monnext, /monplanning…)
- Lancer un duel (/duel), gagner un duel (événement)
- Gagner un quiz (événement)
- Gagner un niveau (événement)
- Combo: utiliser X commandes différentes dans la journée

Récompenses adaptées à la difficulté (EASY/MEDIUM/HARD).
"""

from __future__ import annotations
import os, json, random
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from modules import core

STREAK_PATH   = "data/streaks.json"
MISSIONS_PATH = "data/missions.json"

# ----------------- helpers -----------------
def _bar(current: int, goal: int, width: int = 20) -> str:
    goal = max(1, int(goal or 1))
    cur  = max(0, min(int(current or 0), goal))
    fill = int(round(width * cur / goal))
    return "▰" * fill + "▱" * (width - fill)

def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

# ------------- Mission templates -------------
# (key, label_template, commands_set, base_goal, difficulty)
MISSION_TEMPLATES: List[Tuple[str, str, set, int, str]] = [
    # Suivi AniList
    ("use_next",      "Utilise `/next` ou `/monnext` aujourd'hui", {"next", "monnext"}, 1, "EASY"),
    ("use_planning",  "Consulte ton planning (`/planning` ou `/monplanning`)", {"planning", "monplanning"}, 1, "EASY"),
    ("use_3_tracking","Utilise 3 commandes de suivi différentes (`/next`, `/planning`, `/monplanning`, `/monnext`)", {"next","planning","monplanning","monnext"}, 3, "MEDIUM"),

    # Duel
    ("duel_initiate", "Propose quelqu’un en duel avec `/duel`", {"duel"}, 1, "EASY"),
    ("duel_win",      "Remporte un duel aujourd’hui", {"_custom:duel_win"}, 1, "HARD"),

    # Quiz
    ("quiz_play",     "Participe à un quiz avec `/animequiz`", {"animequiz"}, 1, "EASY"),
    # accepte win solo ET seuil multi
    ("quiz_win",      "Gagne un quiz aujourd’hui", {"_custom:quiz_win", "_custom:quiz_solo_ok"}, 1, "MEDIUM"),

    # Progression / XP
    ("level_up",      "Gagne un niveau aujourd’hui", {"_custom:level_up"}, 1, "HARD"),

    # Social doux
    ("react_quiz",    "Réagis à un quiz avec un emoji aujourd’hui", {"_custom:react_quiz"}, 1, "EASY"),
]

# Barème de récompenses selon difficulté (min, max)
REWARD_TABLE = {
    "EASY":   (20, 35),
    "MEDIUM": (45, 65),
    "HARD":   (80, 120),
}
DEFAULT_REWARD_FALLBACK = 20

# Aide courte affichée par /mission (clé = mission["key"])
MISSION_HINTS: Dict[str, str] = {
    "use_next": "Lance **`/next`** ou **`/monnext`** une fois dans ce serveur.",
    "use_planning": "Ouvre **`/planning`** ou **`/monplanning`** pour consulter les sorties.",
    "use_3_tracking": "Combien **3** commandes différentes parmi : `/next`, `/planning`, `/monplanning`, `/monnext`.",
    "duel_initiate": "Lance un duel avec **`/duel @quelqu’un`** (la partie doit démarrer).",
    "duel_win": "Remporte **au moins une manche** d’un duel aujourd’hui (événement en arrière-plan).",
    "quiz_play": "Joue **`/animequiz`** (ou une variante) puis termine une réponse.",
    "quiz_win": "Réponds correctement à un quiz (solo ou manche) **aujourd’hui**.",
    "level_up": "Passe **un niveau** global (XP) dans la journée — continue à jouer / quiz.",
    "react_quiz": "Réagis avec un emoji à un **message de quiz** du bot (embed « quiz »).",
}

def _roll_reward(difficulty: str) -> int:
    lo, hi = REWARD_TABLE.get(difficulty, (DEFAULT_REWARD_FALLBACK, DEFAULT_REWARD_FALLBACK))
    return random.randint(lo, hi)

# ----------------- Cog -----------------
class Engagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.streaks: Dict[str, Dict[str, Any]] = _load_json(STREAK_PATH, {})
        self.missions: Dict[str, Dict[str, Any]] = _load_json(MISSIONS_PATH, {})

    # ------------- DAILY CHECK-IN / STREAK -------------
    @commands.hybrid_command(name="checkin", aliases=["daily", "login"])
    async def checkin(self, ctx: commands.Context):
        """Check-in du jour : augmente ta série (streak) et donne de l’XP."""
        uid = str(ctx.author.id)
        today = _today_str()
        yesterday = _yesterday_str()
        data = self.streaks.get(uid, {"last": None, "streak": 0, "best": 0})

        if data.get("last") == today:
            return await ctx.send("✅ Tu as **déjà** fait ton check-in aujourd’hui.")

        if data.get("last") == yesterday:
            data["streak"] = int(data.get("streak", 0)) + 1
        else:
            data["streak"] = 1

        data["best"] = max(int(data.get("best", 0)), data["streak"])
        data["last"] = today
        self.streaks[uid] = data
        _save_json(STREAK_PATH, self.streaks)

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
        embed.set_footer(text="Reviens chaque jour pour entretenir ta série !")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="streak")
    async def streak(self, ctx: commands.Context):
        """Affiche ta série quotidienne et ton record."""
        uid = str(ctx.author.id)
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
    def _pick_template(self) -> Tuple[str, str, set, int, str]:
        pool = []
        for tpl in MISSION_TEMPLATES:
            diff = tpl[4]
            weight = 1 if diff == "HARD" else 2 if diff == "MEDIUM" else 3
            pool.extend([tpl] * weight)
        return random.choice(pool)

    def _get_or_create_today_mission(self, uid: str) -> Dict[str, Any]:
        today = _today_str()
        m = self.missions.get(uid)
        if m and m.get("date") == today:
            m.setdefault("difficulty", "EASY")
            m.setdefault("reward_xp", _roll_reward(m.get("difficulty", "EASY")))
            # important : on ne touche PAS à last_reroll ici
            if "commands" in m and isinstance(m["commands"], list):
                m["commands"] = list(set(m["commands"]))
            self.missions[uid] = m
            return m

        # --- on PORTE le last_reroll de la veille (persistance hebdo) ---
        prev = self.missions.get(uid) or {}
        carry_last_rr = prev.get("last_reroll")

        key, label, cmds, goal, diff = self._pick_template()
        m = {
            "date": today,
            "key": key,
            "label": label,
            "commands": list(cmds),
            "goal": goal,
            "progress": 0,
            "reward_xp": _roll_reward(diff),
            "difficulty": diff,
            "completed": False,
            "last_reroll": carry_last_rr,  # <-- persiste
        }
        self.missions[uid] = m
        _save_json(MISSIONS_PATH, self.missions)
        return m

    def _mission_bar_line(self, progress: int, goal: int) -> str:
        return f"{_bar(progress, goal)}  **{progress}/{goal}**"

    async def _try_complete_mission(self, ctx: commands.Context):
        """Appelée après chaque commande réussie (listener)."""
        uid = str(ctx.author.id)
        m = self._get_or_create_today_mission(uid)
        if m.get("completed"):
            return

        cmd = (ctx.command.qualified_name if ctx.command else "") or ""
        if cmd in set(m.get("commands", [])):
            m["progress"] = int(m.get("progress", 0)) + 1
            if m["progress"] >= int(m.get("goal", 1)):
                m["completed"] = True
                xp = int(m.get("reward_xp", DEFAULT_REWARD_FALLBACK))
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp)
                await ctx.send(f"🎯 **Mission accomplie !** +{xp} XP")

            self.missions[uid] = m
            _save_json(MISSIONS_PATH, self.missions)

    # ---- /mission avec menu déroulant d’action ----
    @commands.hybrid_command(name="mission", description="Ta mission du jour (afficher / reroll).")
    @app_commands.describe(action="Que veux-tu faire ?")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Afficher", value="show"),
            app_commands.Choice(name="Reroll (1/sem.)", value="reroll"),
        ]
    )
    async def mission(self, ctx: commands.Context, action: Optional[str] = None):
        """Affiche ta mission du jour. `/mission` ou `/mission action: Reroll (1/sem.)`."""
        # normalise si Choice
        if isinstance(action, app_commands.Choice):
            action = action.value

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

            # autorisé → regénère
            key, label, cmds, base_goal, diff = self._pick_template()
            m.update({
                "key": key,
                "label": label,
                "commands": list(cmds),
                "goal": base_goal,
                "progress": 0,
                "reward_xp": _roll_reward(diff),
                "difficulty": diff,
                "completed": False,
                "last_reroll": today.isoformat(),  # <--- marque la semaine
            })
            self.missions[uid] = m
            _save_json(MISSIONS_PATH, self.missions)
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
        hint = MISSION_HINTS.get(mkey, "Réalise l’objectif décrit ci-dessus ; la progression se met à jour automatiquement.")

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
        if m.get("completed"):
            embed.add_field(
                name="Demain",
                value="Une **nouvelle mission** sera tirée après minuit (fuseau du bot). Pense à **`/checkin`** pour la série !",
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
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot:
            return
        try:
            msg = reaction.message
            if msg.partial:
                await msg.fetch()
            if msg.embeds:
                title = (msg.embeds[0].title or "").lower()
                if "quiz" in title:
                    await self._custom_progress(user.id, "_custom:react_quiz")
        except Exception:
            pass

    # Hook générique pour que d’autres cogs poussent une progression:
    #   self.bot.dispatch("mission_progress", user_id, "_custom:duel_win")
    @commands.Cog.listener()
    async def on_mission_progress(self, user_id: int, key: str):
        try:
            await self._custom_progress(user_id, key)
        except Exception:
            pass

    # Si ton système XP dispatch un level up:
    #   self.bot.dispatch("level_up", user_id, new_level)
    @commands.Cog.listener()
    async def on_level_up(self, user_id: int, new_level: int):
        try:
            await self._custom_progress(user_id, "_custom:level_up")
        except Exception:
            pass

    async def _custom_progress(self, uid: int, key: str):
        uid_str = str(uid)
        m = self._get_or_create_today_mission(uid_str)
        if m.get("completed") or key not in set(m.get("commands", [])):
            return

        m["progress"] = int(m.get("progress", 0)) + 1
        if m["progress"] >= int(m.get("goal", 1)):
            m["completed"] = True
            xp = int(m.get("reward_xp", DEFAULT_REWARD_FALLBACK))
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            if user:
                try:
                    await user.send(f"🎯 **Mission accomplie !** +{xp} XP")
                except discord.Forbidden:
                    pass
            await core.add_xp(self.bot, None, uid, xp)

        self.missions[uid_str] = m
        _save_json(MISSIONS_PATH, self.missions)


async def setup(bot: commands.Bot):
    await bot.add_cog(Engagement(bot))
