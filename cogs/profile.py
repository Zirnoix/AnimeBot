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

class BadgesView(View):
    """Boutons info par badge (tooltip via message éphémère)."""
    def __init__(self, badge_infos: List[Tuple[str, str, str]]):
        """
        badge_infos: liste de tuples (badge_id, label_button, payload_json_str)
        payload_json_str contient ce qu'on veut réafficher (pour éviter réeval)
        """
        super().__init__(timeout=60)
        # Limite de Discord: max 25 composants. On garde les top N si besoin.
        for bid, label, payload in badge_infos[:25]:
            self.add_item(self._make_button(bid, label, payload))

    def _make_button(self, bid: str, label: str, payload: str) -> Button:
        btn = Button(label=label, style=discord.ButtonStyle.secondary)
        async def on_click(interaction: discord.Interaction):
            # Le payload contient: name, icon, desc, count, tier, next_threshold
            try:
                data = json.loads(payload)
            except Exception:
                data = {}
            name = data.get("name", "Badge")
            icon = data.get("icon", "🎖️")
            desc = data.get("desc", "")
            count = data.get("count", 0)
            tier = data.get("tier", -1)
            next_th = data.get("next_threshold")
            if tier >= 0:
                progress = f"Niveau **{tier+1}**"
            else:
                progress = "Aucun palier atteint"
            nxt = f"Prochain palier : **{next_th}**" if next_th else "Au palier maximum ✅"
            await interaction.response.send_message(
                f"{icon} **{name}**\n{desc}\n"
                f"Progression : **{count}**\n{progress}\n{nxt}",
                ephemeral=True
            )
        btn.callback = on_click
        return btn

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

        # Couleur barre par paliers (tu peux garder ta logique existante)
        level_colors = [
            (150, "🌈"), (140, "⬜"), (130, "🟫"), (120, "🟪"),
            (110, "🟦"), (100, "🟩"), (90, "🟥"), (80, "🟧"),
            (70, "🟨"), (60, "⬜"), (50, "🟫"), (40, "🟪"),
            (30, "🟦"), (20, "🟥"), (10, "🟦"), (0, "🟩"),
        ]
        color_emoji = next(c for lvl, c in level_colors if level >= lvl)
        bar = (color_emoji if color_emoji != "🌈" else "🌈") * progress + "⬛" * (total_segments - progress)

        # Titres
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
        for bid, spec in badge_def.BADGES.items():
            # Récupère la valeur du compteur
            source = spec.get("source", "")
            count = 0
            if source.startswith("mini:"):
                key = source.split(":", 1)[1]
                count = int(counts.get(key, 0))
            elif source == "streak:days":
                count = int(counts.get("streak_days", 0))

            thresholds = spec["thresholds"]
            icons = spec["icons"]
            tier, next_th = badge_def.evaluate_tier(count, thresholds)

            if tier >= 0:
                # badge débloqué => icône du palier
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
                # Après avoir calculé: count, tier, next_th, icon, spec["name"]
                if next_th:
                    label_text = f"{spec['name']} ({count}/{next_th})"
                else:
                    label_text = f"{spec['name']} ({count}) MAX"
                badge_buttons_payload.append((bid, label_text, json.dumps(payload)))

            else:
                # rien débloqué -> on n’affiche pas, (ou tu peux afficher un icône grisé si tu préfères)
                pass

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

