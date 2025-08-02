"""
Profile and membership card commands.

This cog provides a command to display a user's profile card summarising
their level, XP progress, quiz scores and mini‑game participation.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from restructured_bot.modules import core


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="mycard")
    async def mycard(self, ctx: commands.Context) -> None:
        """Affiche ta carte de membre AnimeBot avec tes statistiques globales.

        La carte résume ton niveau et XP, ton score de quiz et tes points
        accumulés dans les mini‑jeux (quiz, higher/lower, duels, etc.).
        """
        # Level and XP
        levels = core.load_levels()
        user_data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
        xp = user_data.get("xp", 0)
        level = user_data.get("level", 0)
        next_xp = (level + 1) * 100
        # Quiz score
        scores = core.load_scores()
        quiz_score = scores.get(str(ctx.author.id), 0)
        # Mini-games
        mini_scores = core.get_mini_scores(ctx.author.id)
        # Avatar URL
        avatar_url = None
        try:
            avatar_url = ctx.author.avatar.url
        except Exception:
            avatar_url = None
        try:
            buf = core.generate_profile_card(
                user_name=ctx.author.display_name,
                avatar_url=avatar_url,
                level=level,
                xp=xp,
                next_xp=next_xp,
                quiz_score=quiz_score,
                mini_scores=mini_scores,
            )
            file = discord.File(buf, filename="mycard.jpg")
            embed = discord.Embed(color=discord.Color.dark_orange())
            embed.set_image(url="attachment://mycard.jpg")
            await ctx.send(embed=embed, file=file)
        except Exception:
            # Fallback text representation
            lines = [
                f"🎴 Carte Membre – {ctx.author.display_name}",
                f"Niveau : {level}",
                f"XP : {xp}/{next_xp}",
                f"Score Quiz : {quiz_score}",
            ]
            if mini_scores:
                lines.append("Mini‑jeux :")
                # Human‑readable names for mini‑games
                mapping = {
                    "animequiz": "Quiz",
                    "higherlower": "Higher/Lower",
                    "highermean": "Higher/Mean",
                    "guessyear": "Guess Year",
                    "guessepisodes": "Guess Episodes",
                    "guessgenre": "Guess Genre",
                    "duel": "Duel",
                }
                for g, v in mini_scores.items():
                    # Default to capitalised key if not mapped
                    name = mapping.get(g, g.replace("_", " ").capitalize())
                    lines.append(f"- {name} : {v}")
            await ctx.send("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
