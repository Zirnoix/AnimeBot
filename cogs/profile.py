# cogs/profile.py (ajoute ces imports)
from __future__ import annotations
from typing import Dict, Any, List, Tuple
import json, os
import discord
from discord.ext import commands
from discord.ui import View, Button
from modules import core
from modules.badges import BADGES, evaluate_tier

STREAK_PATH = "data/streaks.json"

def _load_streak(uid: int) -> int:
    """Lit la streak actuelle depuis data/streaks.json (si présent)."""
    try:
        with open(STREAK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        info = data.get(str(uid)) or {}
        return int(info.get("streak", 0))
    except Exception:
        return 0

def _get_user_counts(uid: int) -> Dict[str, int]:
    """
    Agrège les compteurs nécessaires aux badges.
    - mini-scores: via core.get_mini_scores(uid)
    - streak: via data/streaks.json
    """
    counts: Dict[str, int] = {}
    mini = core.get_mini_scores(uid) or {}  # ex: {"animequiz": 12, "guessgenre": 44, ...}
    # map mini-scores
    for k in ["animequiz", "animequizmulti", "guessgenre", "guessyear"]:
        counts[k] = int(mini.get(k, 0))
    # streak
    counts["streak_days"] = _load_streak(uid)
    return counts

def _get_user_counts(user_id: int) -> dict:
    """
    Agrège les compteurs utilisés par les badges :
    - mini-jeux: via core.get_mini_scores(user_id)
    - streak:    via data/streaks.json (si présent)
    """
    counts = core.get_mini_scores(user_id) or {}
    # ajoute streak_days
    try:
        with open("data/streaks.json", "r", encoding="utf-8") as f:
            streaks = json.load(f)
        entry = streaks.get(str(user_id), {})
        counts["streak_days"] = int(entry.get("streak", 0))
    except Exception:
        counts["streak_days"] = 0
    return counts


class BadgesView(discord.ui.View):
    """Boutons 'info' pour badges : affiche une infobulle (ephemeral) avec le prochain palier."""
    def __init__(self, payloads: List[Tuple[str, str, str]]):
        """
        payloads: [(badge_id, label_text, json_payload), ...]
        On limite à 5 boutons pour éviter de surcharger l’embed.
        """
        super().__init__(timeout=60)
        for bid, label, payload in payloads[:5]:
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"badge:{bid}"
            )
            async def on_click(interaction: discord.Interaction, payload=payload):
                try:
                    data = json.loads(payload)
                except Exception:
                    return await interaction.response.send_message("❌ Erreur de badge.", ephemeral=True)

                name = data.get("name", "Badge")
                desc = data.get("desc", "")
                count = data.get("count", 0)
                next_th = data.get("next_threshold")
                tier = int(data.get("tier", -1)) + 1  # tiers humains: 0→“aucun”, 1→bronze…
                nxt = f"{count}/{next_th}" if next_th else "MAX atteint"
                txt = (
                    f"**{name}**\n{desc}\n"
                    f"Palier actuel : **{tier}**\n"
                    f"Progression : **{nxt}**"
                )
                await interaction.response.send_message(txt, ephemeral=True)

            btn.callback = on_click
            self.add_item(btn)

# ... ta classe Profile existe déjà, on complète la commande mycard
class Profile(commands.Cog):
    # ... __init__ etc. inchangés

    @commands.command(name="mycard")
    async def mycard(self, ctx: commands.Context) -> None:
        """Affiche une carte de membre stylée avec les statistiques globales + badges."""
        user_id_str = str(ctx.author.id)
        user_id = ctx.author.id
    
        # Chargement données de progression
        levels = core.load_levels()
        user_data = levels.get(user_id_str, {"xp": 0, "level": 0})
        xp = user_data.get("xp", 0)
        level = user_data.get("level", 0)
        next_xp = core.xp_for_next_level(level)
    
        # Progression (20 segments)
        total_segments = 20
        progress = max(0, min(total_segments, int((xp / max(1, next_xp)) * total_segments)))
    
        # Couleur barre par paliers
        level_colors = [
            (150, "🌈"), (140, "⬜"), (130, "🟫"), (120, "🟪"),
            (110, "🟦"), (100, "🟩"), (90, "🟥"), (80, "🟧"),
            (70, "🟨"), (60, "⬜"), (50, "🟫"), (40, "🟪"),
            (30, "🟦"), (20, "🟥"), (10, "🟦"), (0, "🟩"),
        ]
        color_emoji = next(c for lvl, c in level_colors if level >= lvl)
        filled = color_emoji * progress
        empty = "⬛" * (total_segments - progress)
        bar = filled + empty
    
        # Titre global
        title = core.get_title_for_global_level(level)
    
        # Score quiz + mini-jeux
        scores = core.load_scores()
        quiz_score = scores.get(user_id_str, 0)
        mini_scores = core.get_mini_scores(user_id)
    
        # ======== BADGES ========
        counts = _get_user_counts(user_id)
        shown_badges: List[str] = []
        badge_line_parts: List[str] = []
        badge_buttons_payload: List[Tuple[str, str, str]] = []
    
        # Pour chaque badge défini, calcule le palier débloqué et prépare l’affichage
        for bid, spec in BADGES.items():
            source = spec.get("source", "")
            count = 0
            if source.startswith("mini:"):
                key = source.split(":", 1)[1]
                count = int(counts.get(key, 0))
            elif source == "streak:days":
                count = int(counts.get("streak_days", 0))
    
            thresholds = spec["thresholds"]
            icons = spec["icons"]
            tier, next_th = evaluate_tier(count, thresholds)
    
            if tier >= 0:
                icon = icons[tier] if tier < len(icons) else "🎖️"
                badge_line_parts.append(icon)
                shown_badges.append(bid)
                payload = {
                    "name": spec["name"],
                    "icon": icon,
                    "desc": spec["desc"],
                    "count": count,
                    "tier": tier,
                    "next_threshold": next_th,
                }
                if next_th:
                    label_text = f"{spec['name']} ({count}/{next_th})"
                else:
                    label_text = f"{spec['name']} ({count}) MAX"
                badge_buttons_payload.append((bid, label_text, json.dumps(payload)))
            # sinon: pas encore atteint → on n’affiche pas
    
        # Embed final
        embed = discord.Embed(
            title=f"🎴 Profil de {ctx.author.display_name}",
            color=discord.Color.from_rgb(255 - min(level * 2, 200), 100 + min(level, 100), 30)
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
    
        embed.add_field(name="🎖️ Titre", value=title, inline=True)
        embed.add_field(name="🧬 Niveau", value=f"{level}", inline=True)
        embed.add_field(name="🧪 XP", value=f"{xp} / {next_xp}", inline=True)
        embed.add_field(name="📈 Progression", value=bar, inline=False)
        embed.add_field(name="🏆 Score Quiz", value=f"{quiz_score}", inline=True)
    
        if mini_scores:
            mapping = {
                "animequiz": "Quiz Solo",
                "animequizmulti": "Quiz Multi",
                "higherlower": "Higher/Lower",
                "highermean": "Higher/Mean",
                "guessyear": "Guess Year",
                "guessepisodes": "Guess Episodes",
                "guessgenre": "Guess Genre",
                "duel": "Duel",
            }
            value = ""
            for g, v in mini_scores.items():
                name = mapping.get(g, g.replace("_", " ").capitalize())
                value += f"• **{name}** : {v}\n"
            embed.add_field(name="🎮 Mini-jeux", value=value, inline=False)
    
        # Badges (ligne d’icônes) + boutons “info”
        if badge_line_parts:
            embed.add_field(name="🎖️ Badges", value=" ".join(badge_line_parts), inline=False)
            view = BadgesView(badge_buttons_payload)
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))

