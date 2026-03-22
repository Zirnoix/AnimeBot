# cogs/profile.py — mycard en onglets + mybadges
from __future__ import annotations

import json
from typing import Dict, Any

import discord
from discord.ext import commands

from modules import core
from modules.badges import BADGES, evaluate_tier
from modules.emoji_utils import get_emoji


# ---------- HELPERS BADGES ----------
def _get_user_counts(user_id: int) -> dict:
    """
    Agrège les compteurs utilisés par les badges :
    - mini-jeux: via core.get_mini_scores(user_id)
    - streak:    via data/streaks.json
    - anilist:   via compte AniList lié
    - time:      via data/time_counters.json (facultatif)
    - command:   via data/command_usage.json (facultatif)
    """
    counts = core.get_mini_scores(user_id) or {}

    # --- STREAK ---
    try:
        with open("data/streaks.json", "r", encoding="utf-8") as f:
            streaks = json.load(f)
        entry = streaks.get(str(user_id), {})
        counts["streak_days"] = int(entry.get("streak", 0))
    except Exception:
        counts["streak_days"] = 0
    counts["streak_year"] = counts["streak_days"]  # pour 'streak:year'

    # --- ANILIST ---
    username = None
    try:
        username = getattr(core, "get_linked_anilist", lambda _uid: None)(user_id)
    except Exception:
        username = None
    counts["anilist_linked"] = 1 if username else 0  # pour 'anilist:linked'

    if username:
        stats: Dict[str, Any] = {}
        for fn_name in ("get_anilist_stats", "fetch_anilist_stats"):
            fn = getattr(core, fn_name, None)
            if callable(fn):
                try:
                    stats = fn(username) or {}
                    break
                except Exception:
                    pass
        if not stats:
            try:
                query = """
                query($userName:String){
                  MediaListCollection(userName:$userName, type: ANIME){
                    lists { entries { status } }
                  }
                }
                """
                data = core.query_anilist(query, {"userName": username})
                lists = (data or {}).get("data", {}).get("MediaListCollection", {}).get("lists", []) or []
                total_entries = sum(len(l.get("entries", [])) for l in lists)
                completed = sum(
                    1 for l in lists for e in l.get("entries", []) if str(e.get("status","")).upper()=="COMPLETED"
                )
                watching = sum(
                    1 for l in lists for e in l.get("entries", []) if str(e.get("status","")).upper()=="CURRENT"
                )
                stats = {"total_entries": total_entries, "completed": completed, "current": watching}
            except Exception:
                stats = {}

        counts["anilist_completed"] = int(stats.get("completed", 0))
        counts["anilist_entries"]   = int(stats.get("total_entries", 0))
        counts["anilist_current"]   = int(stats.get("current", 0))

    # --- TIME WINDOWS (facultatif)
    try:
        with open("data/time_counters.json", "r", encoding="utf-8") as f:
            tdata = json.load(f)
        u = tdata.get(str(user_id), {})
        counts["time_morning"] = int(u.get("morning", 0))  # 6h-10h
        counts["time_night"]   = int(u.get("night", 0))    # 0h-4h
    except Exception:
        counts.setdefault("time_morning", 0)
        counts.setdefault("time_night", 0)

    # --- COMMAND USAGE (facultatif)
    try:
        with open("data/command_usage.json", "r", encoding="utf-8") as f:
            cdata = json.load(f)
        u = cdata.get(str(user_id), {})
        counts["command_planning"]   = int(u.get("planning", 0))
        counts["command_decouverte"] = int(u.get("decouverte", 0))
    except Exception:
        counts.setdefault("command_planning", 0)
        counts.setdefault("command_decouverte", 0)

    return counts


# ---------- HELPERS D'AFFICHAGE ----------
def _xp_bar(xp: int, next_xp: int, seg: int = 20) -> str:
    if next_xp <= 0:
        return "⬛" * seg
    progress = max(0, min(seg, int((xp / next_xp) * seg)))
    return "🟦" * progress + "⬛" * (seg - progress)


def _fmt_number(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _mini_table(mini_scores: dict) -> str:
    if not mini_scores:
        return "—"
    labels = {
        "animequiz": "AnimeQuiz (Solo)",
        "animequizmulti": "AnimeQuiz (Multi)",
        "higherlower": "Higher/Lower",
        "guessyear": "Guess Year",
        "guessepisodes": "Guess Episodes",
        "guessgenre": "Guess Genre",
        "guesscharacter": "Guess Character",
        "guessop": "Guess OP",
        "duel": "Duel",
        "duel_victory": "Duel victory",
        "guesspop": "GuessPop",
        "guesspo": "GuessPo",
        "guessspo": "GuessSpo",
        "guessopener": "OP Challenger",
    }
    lines = [
        f"• **{labels.get(k, k.replace('_',' ').title())}** : {_fmt_number(v)}"
        for k, v in sorted(mini_scores.items(), key=lambda x: x[0])
    ]
    return "\n".join(lines[:25])


def _build_badges(bot, counts: dict):
    """Retourne (icons, upcoming, buttons_payload). Ici buttons_payload inutile mais conservé pour compat."""
    icons = []
    upcoming = []
    buttons_payload = []  # non utilisé (on a retiré les boutons info)

    for bid, spec in BADGES.items():
        source = spec.get("source", "")

        # lire compteur en fonction de la source
        if source.startswith("mini:"):
            key = source.split(":", 1)[1]; count = int(counts.get(key, 0))
        elif source.startswith("streak:"):
            key = source.split(":", 1)[1]; count = int(counts.get(f"streak_{key}", counts.get("streak_days", 0)))
        elif source.startswith("anilist:"):
            key = source.split(":", 1)[1]; count = int(counts.get(f"anilist_{key}", 0))
        elif source.startswith("time:"):
            key = source.split(":", 1)[1]; count = int(counts.get(f"time_{key}", 0))
        elif source.startswith("command:"):
            key = source.split(":", 1)[1]; count = int(counts.get(f"command_{key}", 0))
        else:
            count = 0

        thresholds = spec["thresholds"]
        icon_list = spec["icons"]
        tier, next_th = evaluate_tier(count, thresholds)

        # ignorer les hidden non débloqués (ils ne doivent pas apparaître dans mycard)
        if spec.get("hidden", False) and (tier is None or tier < 0):
            continue

        if tier is not None and tier >= 0:
            icon = icon_list[tier] if tier < len(icon_list) else "🎖️"
            custom = spec.get("icons_custom")
            if custom and tier < len(custom):
                resolved = get_emoji(bot, custom[tier], fallback=None)
                if resolved:
                    icon = resolved
            icons.append(icon)
        else:
            # Non débloqué & visible → “À venir”
            if not spec.get("hidden", False) and thresholds:
                need = thresholds[0]
                upcoming.append((spec["name"], count, need, max(0, need - count), spec.get("desc", "")))

    upcoming.sort(key=lambda x: x[3])
    return icons, upcoming[:5], buttons_payload


# ---------- VUE À ONGLETS ----------
class MyCardTabs(discord.ui.View):
    """Vue simplifiée : seulement les onglets (pas de boutons d'info badges)."""
    def __init__(self, author: discord.abc.User, data: dict):
        super().__init__(timeout=120)
        self.author = author
        self.data = data
        # Onglets
        self.add_item(discord.ui.Button(label="Aperçu", style=discord.ButtonStyle.primary, custom_id="tab:overview"))
        self.add_item(discord.ui.Button(label="Mini-jeux", style=discord.ButtonStyle.secondary, custom_id="tab:minis"))
        self.add_item(discord.ui.Button(label="Badges", style=discord.ButtonStyle.secondary, custom_id="tab:badges"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce panneau n’est pas pour toi.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            if isinstance(c, discord.ui.Button):
                c.disabled = True


# ---------- BUILD DES EMBEDS ----------
def _embed_overview(ctx, level, xp, next_xp, title, quiz_score, streak_days):
    bar = _xp_bar(xp, next_xp)
    e = discord.Embed(title=f"🎴 Profil de {ctx.author.display_name}", color=discord.Color.blurple())
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    e.add_field(name="🎖️ Titre", value=title, inline=True)
    e.add_field(name="🧬 Niveau", value=str(level), inline=True)
    e.add_field(name="🧪 XP", value=f"{_fmt_number(xp)} / {_fmt_number(next_xp)}", inline=True)
    e.add_field(name="📈 Progression", value=bar, inline=False)
    e.add_field(name="🏆 Score Quiz", value=str(_fmt_number(quiz_score)), inline=True)

    # Streak
    next_pal = None
    for t in sorted(BADGES.get("streak", {}).get("thresholds", [])):
        if streak_days < t:
            next_pal = t
            break
    streak_line = f"🔥 Série actuelle : **{streak_days}** jour(s)"
    if next_pal:
        streak_line += f" • Prochain palier : **{streak_days}/{next_pal}**"
    e.add_field(name="🔥 Streak", value=streak_line, inline=False)
    return e


def _embed_minis(ctx, mini_scores):
    e = discord.Embed(title="🎮 Mini-jeux", color=discord.Color.dark_theme())
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    e.description = _mini_table(mini_scores)
    return e


def _embed_badges(ctx, icons, upcoming):
    e = discord.Embed(title="🎖️ Badges", color=discord.Color.gold())
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    e.add_field(name="Débloqués", value=(" ".join(icons) if icons else "— Aucun"), inline=False)
    if upcoming:
        lines = []
        for (n, c, need, _miss, desc) in upcoming:
            lines.append(f"• **{n}** — {c}/{need} (reste {need - c})\n_{desc}_")
        e.add_field(name="À venir", value="\n".join(lines), inline=False)
    return e


# ---------- COG ----------
class Profile(commands.Cog):
    """Profil + stats + badges (onglets) + commande mybadges dédiée."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="mycard", description="Affiche ta carte de membre (onglets)")
    async def mycard(self, ctx: commands.Context) -> None:
        user_id = ctx.author.id
        user_id_str = str(user_id)

        # Données globales
        levels = core.load_levels()
        user_data = levels.get(user_id_str, {"xp": 0, "level": 0})
        xp = int(user_data.get("xp", 0))
        level = int(user_data.get("level", 0))
        next_xp = core.xp_for_next_level(level)
        title = core.get_title_for_global_level(level)

        scores = core.load_scores()
        quiz_score = int(scores.get(user_id_str, 0))
        mini_scores = core.get_mini_scores(user_id) or {}

        counts = _get_user_counts(user_id)
        streak_days = int(counts.get("streak_days", 0))

        # Badges (sans hidden dans mycard)
        icons, upcoming, _ = _build_badges(self.bot, counts)

        # Page 1 par défaut
        embed = _embed_overview(ctx, level, xp, next_xp, title, quiz_score, streak_days)
        view = MyCardTabs(ctx.author, {
            "overview": (level, xp, next_xp, title, quiz_score, streak_days),
            "minis": mini_scores,
            "badges": (icons, upcoming)
        })

        # Routeur d’onglets
        async def on_interaction(inter: discord.Interaction):
            cid = inter.data.get("custom_id", "")
            if cid == "tab:overview":
                e = _embed_overview(ctx, *view.data["overview"])
                await inter.response.edit_message(embed=e, view=view)
            elif cid == "tab:minis":
                e = _embed_minis(ctx, view.data["minis"])
                await inter.response.edit_message(embed=e, view=view)
            elif cid == "tab:badges":
                icons_, upcoming_ = view.data["badges"]
                e = _embed_badges(ctx, icons_, upcoming_)
                await inter.response.edit_message(embed=e, view=view)

        for c in view.children:
            if isinstance(c, discord.ui.Button) and c.custom_id and c.custom_id.startswith("tab:"):
                c.callback = on_interaction

        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="mybadges", description="Liste tes badges et ta progression")
    async def mybadges(self, ctx: commands.Context) -> None:
        user_id = ctx.author.id
        counts = _get_user_counts(user_id)
        unlocked_lines = []
        locked_lines = []

        for _bid, spec in BADGES.items():
            source = spec.get("source", "")
            # compteur
            if source.startswith("mini:"):
                key = source.split(":", 1)[1]; count = int(counts.get(key, 0))
            elif source.startswith("streak:"):
                key = source.split(":", 1)[1]; count = int(counts.get(f"streak_{key}", counts.get("streak_days", 0)))
            elif source.startswith("anilist:"):
                key = source.split(":", 1)[1]; count = int(counts.get(f"anilist_{key}", 0))
            elif source.startswith("time:"):
                key = source.split(":", 1)[1]; count = int(counts.get(f"time_{key}", 0))
            elif source.startswith("command:"):
                key = source.split(":", 1)[1]; count = int(counts.get(f"command_{key}", 0))
            else:
                count = 0

            thresholds = spec["thresholds"]
            icon_list = spec["icons"]
            tier, next_th = evaluate_tier(count, thresholds)

            if spec.get("hidden", False) and (tier is None or tier < 0):
                # hidden non débloqué → afficher ??? côté mybadges
                if thresholds:
                    need = thresholds[0]
                    locked_lines.append(f"• ??? — {count}/{need} (reste {need - count})")
                continue

            if tier is not None and tier >= 0:
                icon = icon_list[tier] if tier < len(icon_list) else "🎖️"
                custom = spec.get("icons_custom")
                if custom and tier < len(custom):
                    resolved = get_emoji(self.bot, custom[tier], fallback=None)
                    if resolved:
                        icon = resolved
                prog = f"{count}/{next_th}" if next_th else "MAX"
                unlocked_lines.append(f"{icon} **{spec['name']}** — palier **{tier+1}** · {prog}\n_{spec['desc']}_")
            else:
                if thresholds:
                    need = thresholds[0]
                    # badge visible non débloqué → avec description
                    locked_lines.append(f"• **{spec['name']}** — {count}/{need} (reste {need - count})\n_{spec['desc']}_")

        e = discord.Embed(title=f"🎖️ Badges de {ctx.author.display_name}", color=discord.Color.gold())
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        e.add_field(name="Débloqués", value=("\n".join(unlocked_lines) if unlocked_lines else "— Aucun pour l’instant"), inline=False)
        if locked_lines:
            e.add_field(name="À venir", value="\n".join(locked_lines[:20]), inline=False)
        await ctx.send(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
