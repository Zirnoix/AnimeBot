import discord
from discord.ext import commands
import random
import json
import os
from modules.anilist import get_random_anime_title
from modules.title_cache import save_title_cache
from modules.utils import get_user_level_title
from modules.images import generate_rank_card

SCORES_FILE = "data/quiz_scores.json"

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def load_scores(self):
        if not os.path.exists(SCORES_FILE):
            return {}
        with open(SCORES_FILE, "r") as f:
            return json.load(f)

    def save_scores(self, scores):
        with open(SCORES_FILE, "w") as f:
            json.dump(scores, f, indent=4)

    @commands.command(name="animequiz")
    async def animequiz(self, ctx):
        anime = get_random_anime_title()
        if not anime:
            await ctx.send("❌ Impossible de trouver un anime.")
            return

        title = anime['correct_title']
        image_url = anime['image_url']
        options = anime['options']

        embed = discord.Embed(
            title="🎮 Anime Quiz",
            description="Quel est cet anime ?",
            color=discord.Color.purple()
        )
        embed.set_image(url=image_url)

        view = discord.ui.View(timeout=30)

        for option in options:
            view.add_item(discord.ui.Button(label=option, style=discord.ButtonStyle.secondary))

        await ctx.send(embed=embed, view=view)
        # Logique de scoring à rajouter dans interaction selon réponse.

    @commands.command(name="quiztop")
    async def quiztop(self, ctx):
        scores = self.load_scores()
        if not scores:
            await ctx.send("🏆 Aucun score enregistré pour l’instant.")
            return

        leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]

        def get_title(score):
            if score >= 100:
                return "🌌 Légende"
            elif score >= 80:
                return "🔥 Champion"
            elif score >= 60:
                return "🎯 Expert"
            elif score >= 40:
                return "📚 Connaisseur"
            elif score >= 20:
                return "🌱 Amateur"
            else:
                return "👶 Débutant"

        desc = ""
        for i, (uid, score) in enumerate(leaderboard, 1):
            user = await self.bot.fetch_user(int(uid))
            desc += f"**{i}.** {user.mention} - {score} XP ({get_title(score)})\n"

        embed = discord.Embed(title="🏆 Classement Quiz", description=desc, color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def myrank(self, ctx):
        scores = self.load_scores()
        xp = scores.get(str(ctx.author.id), 0)
        title = get_user_level_title(xp)

        image = await generate_rank_card(ctx.author, xp, title)
        if image:
            await ctx.send(file=image)
        else:
            await ctx.send(f"{ctx.author.mention}, tu as {xp} XP - {title}.")

async def setup(bot):
    await bot.add_cog(Quiz(bot))
