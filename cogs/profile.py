# cogs/profile.py

import discord
from discord.ext import commands
from modules.xp_manager import get_xp, get_rank_title
from modules.score_manager import get_user_scores
from modules.image import generate_profile_card
import asyncio

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mycard")
    async def mycard(self, ctx):
        """📇 Affiche ta carte de profil"""
        user_id = str(ctx.author.id)

        # XP + Rang
        xp = get_xp(user_id)
        rank = get_rank_title(xp)

        # Scores mini-jeux
        scores = get_user_scores(user_id)
        total_quiz = scores.get("animequiz", 0)
        total_year = scores.get("guessyear", 0)
        total_genre = scores.get("guessgenre", 0)
        total_episode = scores.get("guessepisode", 0)
        total_character = scores.get("guesscharacter", 0)
        total_op = scores.get("guessop", 0)

        # Badges à afficher
        badges = []
        if total_quiz >= 10: badges.append("🎓 Quiz Master")
        if total_year >= 5: badges.append("📅 Time Traveler")
        if total_op >= 3: badges.append("🎵 Audio Addict")
        if xp >= 500: badges.append("🏅 XP Warrior")

        # Image à générer
        image_bytes = await asyncio.to_thread(generate_profile_card,
            username=str(ctx.author),
            avatar_url=ctx.author.display_avatar.url,
            xp=xp,
            rank=rank,
            quiz_score=total_quiz,
            year_score=total_year,
            genre_score=total_genre,
            episode_score=total_episode,
            character_score=total_character,
            op_score=total_op,
            badges=badges
        )

        file = discord.File(image_bytes, filename="mycard.png")
        embed = discord.Embed(
            title=f"📇 Profil de {ctx.author.display_name}",
            color=0x1abc9c
        )
        embed.set_image(url="attachment://mycard.png")
        await ctx.send(embed=embed, file=file)

async def setup(bot):
    await bot.add_cog(Profile(bot))
