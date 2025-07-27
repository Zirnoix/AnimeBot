from discord.ext import commands
import discord
from modules.utils import get_user_level, load_json, save_json
from modules.title_cache import get_random_anime_data
import random

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx):
        anime = get_random_anime_data()
        if not anime:
            await ctx.send("❌ Impossible de récupérer un anime.")
            return

        embed = discord.Embed(title="🎮 Anime Quiz", description="Devine l’anime à partir de cette image !", color=0x1abc9c)
        embed.set_image(url=anime["image"])
        embed.set_footer(text="Réponds en tapant le nom de l’anime !")

        await ctx.send(embed=embed)

    @commands.command(name="quiztop")
    async def quiz_top(self, ctx):
        scores = load_json("data/quiz_scores.json")
        leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]

        if not leaderboard:
            await ctx.send("📉 Aucun score enregistré.")
            return

        description = ""
        for i, (uid, score) in enumerate(leaderboard, 1):
            level = get_user_level(score)
            user = await self.bot.fetch_user(int(uid))
            description += f"**{i}.** {user.name} — {score} XP ({level})\n"

        embed = discord.Embed(title="🏆 Classement Quiz", description=description, color=0xf1c40f)
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def my_rank(self, ctx):
        from modules.images import create_xp_image
        scores = load_json("data/quiz_scores.json")
        score = scores.get(str(ctx.author.id), 0)
        level = get_user_level(score)
        path = create_xp_image(ctx.author.name, level, score)
        file = discord.File(path, filename="rank.png")
        await ctx.send(file=file)

async def setup(bot):
    await bot.add_cog(Quiz(bot))
