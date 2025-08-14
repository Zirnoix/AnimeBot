# cogs/profile.py
from __future__ import annotations

import json
from typing import List, Tuple

import discord
from discord.ext import commands

from modules import core
from modules.badges import BADGES, evaluate_tier


# ---------- HELPERS BADGES ----------
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
                tier = int(data.get("tier", -1)) + 1  # 0→aucun, 1→palier1, etc.
                nxt = f"{count}/{next_th}" if next_th else "MAX atteint"
                txt = (
                    f"**{name}**\n{desc}\n"
                    f"Palier actuel : **{tier}**\n"
                    f"Progression : **{nxt}**"
                )
                await interaction.response.send_message(txt, ephemeral=True)

            btn.callback = on_click
            self.add_item(btn)


# ---------- COG ----------
class Profile(commands.Cog):
    """Profil + stats + badges."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="mycard")
    async def mycard(self, ctx: commands.Context) -> None:
        """Affiche une carte de membre stylée avec les statistiques globales + badges."""
        user_id_str = str(ctx.author.id)
        user_id = ctx.author.id

        # Progression
        levels = core.load_levels()
        user_data = levels.get(user_id_str, {"xp": 0, "level": 0})
        xp = user_data.get("xp", 0)
        level = user_data.get("level", 0)
        next_xp = core.xp_for_next_level(level)

        total_segments = 20
        progress = max(0, min(total_segments, int((xp / max(1, next_xp)) * total_segments)))

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

        title = core.get_title_for_global_level(level)

        scores = core.load_scores()
        quiz_score = scores.get(user_id_str, 0)
        mini_scores = core.get_mini_scores(user_id)

        # ======== BADGES ========
        counts = _get_user_counts(user_id)
        badge_line_parts: List[str] = []
        badge_buttons_payload: List[Tuple[str, str, str]] = []

        for bid, spec in BADGES.items():
            source = spec.get("source", "")
            if source.startswith("mini:"):
                key = source.split(":", 1)[1]
                count = int(counts.get(key, 0))
            elif source == "streak:days":
                count = int(counts.get("streak_days", 0))
            else:
                count = 0

            thresholds = spec["thresholds"]
            icons = spec["icons"]
            tier, next_th = evaluate_tier(count, thresholds)

            if tier >= 0:
                icon = icons[tier] if tier < len(icons) else "🎖️"
                badge_line_parts.append(icon)
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

        # Embed
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

        # Badges (ligne + boutons)
        if badge_line_parts:
            embed.add_field(name="🎖️ Badges", value=" ".join(badge_line_parts), inline=False)
            view = BadgesView(badge_buttons_payload)
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
