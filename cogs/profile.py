# cogs/profile.py

import discord
from discord.ext import commands
import os

from modules import xp_manager, score_manager, image


class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mycard")
    async def mycard(self, ctx):
        user = ctx.author
        user_id = str(user.id)
        username = user.display_name

        # XP et rang
        xp = xp_manager.get_xp(user_id)
        rank = xp_manager.get_rank_title(xp)

        # Points de quiz
        quiz_score = score_manager.get_quiz_score(user_id)

        # Est-ce qu’il est dans le top quiz ?
        top_users = [uid for uid, _ in score_manager.get_quiz_leaderboard()]
        in_top = user_id in top_users

        # Scores guess
        guess_scores = score_manager.get_user_guess_scores(user_id)

        # Générer l'image
        card_path = f"data/{user_id}_card.png"
        image.save_profile_card(username, rank, quiz_score, in_top, guess_scores, card_path)

        # Envoyer l'image
        file = discord.File(card_path, filename="profile.png")
        embed = discord.Embed(
            title=f"📇 Carte de {username}",
            color=discord.Color.purple()
        )
        embed.set_image(url="attachment://profile.png")
        await ctx.send(file=file, embed=embed)


async def setup(bot):
    await bot.add_cog(Profile(bot))
