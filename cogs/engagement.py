"""
Engagement features: daily check-in (streak) + daily missions.
- !checkin (aliases: !daily, !login)
- !mission            -> show today's mission and progress
- !mission reroll     -> 1 reroll per day
Missions progress is tracked automatically when users run target commands.
"""

from __future__ import annotations
import os, json, random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import discord
from discord.ext import commands

from modules import core

STREAK_PATH   = "data/streaks.json"
MISSIONS_PATH = "data/missions.json"

# ----------------- tiny storage helpers -----------------
def _bar(current: int, goal: int, width: int = 20) -> str:
    goal = max(1, goal)
    fill = max(0, min(width, int(current / goal * width)))
    return "█" * fill + "░" * (width - fill)

def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _today_str() -> str:
    return datetime.now(tz=core.TIMEZONE).strftime("%Y-%m-%d")

def _yesterday_str() -> str:
    d = datetime.now(tz=core.TIMEZONE) - timedelta(days=1)
    return d.strftime("%Y-%m-%d")

# ----------------- missions catalog -----------------
# key, label, target commands (qualified_name)
MISSION_POOL = [
    # Planning / suivi
    ("use_next",        "Utilise `!next` ou `!monnext` aujourd'hui", {"next", "monnext"}),
    ("use_planning",    "Consulte ton planning (`!planning` ou `!monplanning`)", {"planning", "monplanning"}),

    # Découverte
    ("use_decouverte",  "Découvre un anime avec `!decouverte`", {"decouverte", "discover", "randomanime"}),

    # Quiz
    ("quiz_solo",     "Réponds correctement à un quiz solo (`!animequiz`)", {"_custom:quiz_solo_ok"}),
    ("quiz_multi",      "Participe à un quiz multi (`!animequizmulti`)", {"animequizmulti"}),
    ("guess_year",      "Joue à `!guessyear` aujourd'hui", {"guessyear"}),
    ("guess_genre",     "Joue à `!guessgenre` aujourd'hui", {"guessgenre"}),

    # Combos
    ("combo_view",      "Utilise 3 commandes différentes de suivi (`!next`, `!planning`, `!decouverte`) dans la journée", {"next", "monnext", "planning", "monplanning", "decouverte", "discover", "randomanime"}),

    # Social
    ("send_gg",         "Envoie un message contenant 'gg' aujourd'hui", {"_custom:send_gg"}),
    ("react_quiz",      "Réagis à un quiz avec un emoji aujourd'hui", {"_custom:react_quiz"}),
]

DEFAULT_REWARD_XP = 20
DEFAULT_GOAL      = 1

class Engagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.streaks: Dict[str, Dict[str, Any]] = _load_json(STREAK_PATH, {})
        self.missions: Dict[str, Dict[str, Any]] = _load_json(MISSIONS_PATH, {})

    # ------------- DAILY CHECK-IN / STREAK -------------
    @commands.command(name="checkin", aliases=["daily", "login"])
    async def checkin(self, ctx: commands.Context):
        """Check-in du jour : augmente ta série (streak) et donne de l’XP."""
        uid = str(ctx.author.id)
        today = _today_str()
        yesterday = _yesterday_str()
        data = self.streaks.get(uid, {"last": None, "streak": 0, "best": 0})

        if data.get("last") == today:
            return await ctx.send("✅ Tu as **déjà** fait ton check-in aujourd’hui.")

        # calcule la streak
        if data.get("last") == yesterday:
            data["streak"] = int(data.get("streak", 0)) + 1
        else:
            data["streak"] = 1

        # record perso
        data["best"] = max(int(data.get("best", 0)), data["streak"])
        data["last"] = today
        self.streaks[uid] = data
        _save_json(STREAK_PATH, self.streaks)

        # Barème clair (rapide au début, stable ensuite)
        s = data["streak"]
        if s == 1:
            xp = 10
        elif s == 2:
            xp = 15
        elif 3 <= s < 7:
            xp = 20
        else:
            xp = 30  # cap à partir de 7+

        await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp)

        # viz de progression vers le prochain palier “fort” (7, 14, 21…)
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

    @commands.command(name="streak")
    async def streak(self, ctx: commands.Context):
        """Affiche ta série quotidienne et ton record."""
        uid = str(ctx.author.id)
        data = self.streaks.get(uid, {"streak": 0, "best": 0})
        s, b = int(data.get("streak", 0)), int(data.get("best", 0))
        if s <= 0:
            return await ctx.send("📭 Aucune série en cours. Utilise `!daily` pour commencer.")
        next_milestone = ((s // 7) + 1) * 7
        to_next = max(0, next_milestone - s)
        bar = _bar(next_milestone - to_next, next_milestone)
        await ctx.send(
            f"🔥 **Série actuelle : {s}**  |  🏅 **Record : {b}**\n"
            f"Prochain palier **{next_milestone}** : {bar} (reste **{to_next}**)"
        )


    # ------------- DAILY MISSION -------------
    def _get_or_create_today_mission(self, uid: str) -> Dict[str, Any]:
        today = _today_str()
        m = self.missions.get(uid)
        if m and m.get("date") == today:
            return m

        # (re)génère une mission du pool
        key, label, cmds = random.choice(MISSION_POOL)
        m = {
            "date": today,
            "key": key,
            "label": label,
            "commands": list(cmds),
            "goal": DEFAULT_GOAL,
            "progress": 0,
            "reward_xp": DEFAULT_REWARD_XP,
            "rerolled": False,
            "completed": False,
        }
        self.missions[uid] = m
        _save_json(MISSIONS_PATH, self.missions)
        return m

    async def _try_complete_mission(self, ctx: commands.Context):
        """Appelée après chaque commande réussie (listener ci-dessous)."""
        uid = str(ctx.author.id)
        m = self._get_or_create_today_mission(uid)
        if m.get("completed"):
            return

        cmd = ctx.command.qualified_name if ctx.command else ""
        # si la commande matche la mission du jour, on incrémente
        if cmd in set(m.get("commands", [])):
            m["progress"] = int(m.get("progress", 0)) + 1
            # check completion
            if m["progress"] >= int(m.get("goal", DEFAULT_GOAL)):
                m["completed"] = True
                # récompense
                xp = int(m.get("reward_xp", DEFAULT_REWARD_XP))
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp)
                await ctx.send(f"🎯 **Mission accomplie !** +{xp} XP")

            self.missions[uid] = m
            _save_json(MISSIONS_PATH, self.missions)

    @commands.command(name="mission")
    async def mission(self, ctx: commands.Context, action: Optional[str] = None):
        """Affiche ta mission du jour. `!mission reroll` pour changer (1x/jour)."""
        uid = str(ctx.author.id)
        m = self._get_or_create_today_mission(uid)

        if action and action.lower() in {"reroll", "re", "r"}:
            if m.get("rerolled"):
                return await ctx.send("♻️ Tu as déjà reroll ta mission aujourd'hui.")
            # regen
            key, label, cmds = random.choice(MISSION_POOL)
            m.update({
                "key": key, "label": label, "commands": list(cmds),
                "goal": DEFAULT_GOAL, "progress": 0,
                "reward_xp": DEFAULT_REWARD_XP, "rerolled": True, "completed": False
            })
            self.missions[uid] = m
            _save_json(MISSIONS_PATH, self.missions)
            await ctx.send("🔁 Mission rerollée !")

        # Affichage
        done = m.get("progress", 0)
        goal = m.get("goal", DEFAULT_GOAL)
        status = "✅ **Terminée**" if m.get("completed") else "⏳ En cours"
        embed = discord.Embed(
            title="🗒️ Mission du jour",
            description=(
                f"{m['label']}\n"
                f"Progression : **{done}/{goal}**\n"
                f"Récompense : **+{m['reward_xp']} XP**\n"
                f"État : {status}"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    # ------------- listen to commands to track missions -------------

    @commands.Cog.listener()
    async def on_mission_progress(self, user_id: int, key: str):
        # Permet aux autres cogs (quiz) de pousser une progression
        try:
            await self._custom_progress(user_id, key)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        # Ignore bots
        if not ctx or not ctx.command or ctx.author.bot:
            return
        try:
            await self._try_complete_mission(ctx)
        except Exception:
            # on ne casse pas l’exécution si tracking échoue
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if "gg" in message.content.lower():
            await self._custom_progress(message.author.id, "_custom:send_gg")

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

    async def _custom_progress(self, uid: int, key: str):
        """Incrémente la mission si c’est une mission custom."""
        uid = str(uid)
        m = self._get_or_create_today_mission(uid)
        if m.get("completed") or key not in set(m.get("commands", [])):
            return

        m["progress"] = int(m.get("progress", 0)) + 1
        if m["progress"] >= int(m.get("goal", DEFAULT_GOAL)):
            m["completed"] = True
            xp = int(m.get("reward_xp", DEFAULT_REWARD_XP))
            # MP optionnel
            user = self.bot.get_user(int(uid)) or await self.bot.fetch_user(int(uid))
            if user:
                try:
                    await user.send(f"🎯 **Mission accomplie !** +{xp} XP")
                except discord.Forbidden:
                    pass
            # Ajout XP (uid en int, channel=None accepté)
            await core.add_xp(self.bot, None, int(uid), xp)

        self.missions[uid] = m
        _save_json(MISSIONS_PATH, self.missions)


async def setup(bot: commands.Bot):
    await bot.add_cog(Engagement(bot))
