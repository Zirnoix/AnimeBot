# cogs/stats.py

import discord
from discord.ext import commands
from modules.xp_manager import get_xp, get_rank_title
from modules.score_manager import get_user_scores
from modules.image import generate_stats_image
import asyncio

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mystats")
    async def mystats(self, ctx):
        """📊 Affiche tes statistiques générales sur les mini-jeux"""
        user_id = str(ctx.author.id)
        xp = get_xp(user_id)
        rank = get_rank_title(xp)
        scores = get_user_scores(user_id)

        total_score = sum(scores.values())
        badges = 0
        if scores.get("animequiz", 0) >= 10: badges += 1
        if scores.get("guessyear", 0) >= 5: badges += 1
        if scores.get("guessop", 0) >= 3: badges += 1
        if xp >= 500: badges += 1

        image_bytes = await asyncio.to_thread(generate_stats_image,
            username=str(ctx.author),
            avatar_url=ctx.author.display_avatar.url,
            xp=xp,
            rank=rank,
            total_games=total_score,
            scores=scores,
            badges=badges
        )

        file = discord.File(image_bytes, filename="mystats.png")
        embed = discord.Embed(
            title=f"📊 Statistiques de {ctx.author.display_name}",
            color=0x7289da
        )
        embed.set_image(url="attachment://mystats.png")
        await ctx.send(embed=embed, file=file)

async def setup(bot):
    await bot.add_cog(Stats(bot))
