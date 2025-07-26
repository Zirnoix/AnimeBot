import discord
from discord.ext import commands
import json
import random
import requests
import os
from modules.utils import load_json, save_json
from modules.title_cache import get_cached_title, set_cached_title
from modules.images import create_xp_image

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scores_file = "data/quiz_scores.json"
        self.levels_file = "data/quiz_levels.json"
        self.anilist_url = "https://graphql.anilist.co"

    def get_user_level(self, user_id):
        scores = load_json(self.scores_file)
        return scores.get(str(user_id), 0)

    def add_score(self, user_id, amount):
        scores = load_json(self.scores_file)
        scores[str(user_id)] = scores.get(str(user_id), 0) + amount
        save_json(self.scores_file, scores)

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx):
        await ctx.send("🎮 Lancement du quiz...")

        query = f"""
        query {{
          Page(perPage: 1, page: {random.randint(1, 500)}) {{
            media(type: ANIME, isAdult: false, sort: SCORE_DESC) {{
              id
              title {{
                romaji
                english
                native
              }}
              coverImage {{
                large
              }}
            }}
          }}
        }}
        """

        response = requests.post(self.anilist_url, json={"query": query}, headers={"Content-Type": "application/json"})

        if response.status_code != 200:
            await ctx.send("❌ Erreur lors de la récupération de l’anime.")
            return

        anime = response.json()["data"]["Page"]["media"][0]
        titles = [anime["title"]["romaji"], anime["title"]["english"], anime["title"]["native"]]
        titles = [t for t in titles if t]
        correct_title = titles[0]
        set_cached_title(anime["id"], correct_title)

        embed = discord.Embed(title="Devine l’anime !", description="Réponds avec le bon nom !", color=0x3498db)
        embed.set_image(url=anime["coverImage"]["large"])
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for("message", timeout=30.0, check=check)
        except:
            await ctx.send(f"⏱️ Temps écoulé ! C’était : **{correct_title}**")
            return

        if any(t.lower() in msg.content.lower() for t in titles):
            self.add_score(ctx.author.id, 10)
            await ctx.send(f"✅ Bonne réponse {ctx.author.mention} ! Tu gagnes 10 points.")
        else:
            await ctx.send(f"❌ Mauvaise réponse ! C’était : **{correct_title}**")

    @commands.command(name="quiztop")
    async def quiz_top(self, ctx):
        scores = load_json(self.scores_file)
        if not scores:
            await ctx.send("📉 Aucun score enregistré.")
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
            desc += f"**{i}.** {user.name} — {score} pts ({get_title(score)})\n"

        embed = discord.Embed(title="🏆 Classement Quiz", description=desc, color=0x00ff00)
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def my_rank(self, ctx):
        scores = load_json(self.scores_file)
        score = scores.get(str(ctx.author.id), 0)
        rank = sorted(scores.items(), key=lambda x: x[1], reverse=True).index((str(ctx.author.id), score)) + 1
        title = "👶 Débutant"
        if score >= 100:
            title = "🌌 Légende"
        elif score >= 80:
            title = "🔥 Champion"
        elif score >= 60:
            title = "🎯 Expert"
        elif score >= 40:
            title = "📚 Connaisseur"
        elif score >= 20:
            title = "🌱 Amateur"

        image = create_xp_image(ctx.author.name, title, score)
        image.save("data/temp_rank.png")
        file = discord.File("data/temp_rank.png", filename="rank.png")

        embed = discord.Embed(title=f"🎖️ Ton Rang - {ctx.author.name}", description=f"**{title}** — {score} XP", color=0x7289da)
        embed.set_image(url="attachment://rank.png")
        await ctx.send(embed=embed, file=file)

async def setup(bot):
    await bot.add_cog(Quiz(bot))