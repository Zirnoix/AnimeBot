from discord.ext import commands
import discord
import random
import asyncio
import json
import os
from modules.utils import load_json, save_json, normalize_title, get_anilist_user_animelist, get_anime_list, update_score, normalize_title

# ✅ !animequiz – Devine 1 anime
OWNER_USERNAME = os.getenv("ANILIST_USERNAME")

QUIZ_FILE = "quiz_scores.json"

def get_anime_list():
    anime_list = get_anilist_user_animelist(OWNER_USERNAME)
    return [anime["title"]["romaji"] for anime in anime_list]

def update_score(user_id, success):
    scores = load_json(QUIZ_FILE, {})
    if user_id not in scores:
        scores[user_id] = {"points": 0, "games": 0}

    scores[user_id]["games"] += 1
    if success:
        scores[user_id]["points"] += 1

    save_json(QUIZ_FILE, scores)

class AnimeQuiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.anime_list = get_anime_list()

    @commands.command(name="animequiz")
    async def animequiz(self, ctx):
        anime = random.choice(self.anime_list)
        await ctx.send(f"🎲 Quel est cet anime ? `{normalize_title(anime)}` (réponds dans les 15 secondes)")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send(f"⏱️ Temps écoulé ! C'était **{anime}**.")
            update_score(str(ctx.author.id), False)
            return

        if normalize_title(msg.content) == normalize_title(anime):
            await ctx.send("✅ Bonne réponse ! +1 point")
            update_score(str(ctx.author.id), True)
        else:
            await ctx.send(f"❌ Mauvaise réponse ! C'était **{anime}**.")
            update_score(str(ctx.author.id), False)

    @commands.command(name="animequizmulti")
    async def animequizmulti(self, ctx, count: int = 5):
        if count < 5 or count > 20:
            return await ctx.send("❗ Choisis un nombre entre 5 et 20.")

        score = 0
        for _ in range(count):
            anime = random.choice(self.anime_list)
            await ctx.send(f"🎲 `{normalize_title(anime)}`")

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send(f"⏱️ Temps écoulé ! C'était **{anime}**.")
                continue

            if normalize_title(msg.content) == normalize_title(anime):
                score += 1
                await ctx.send("✅")
            else:
                await ctx.send(f"❌ C'était **{anime}**.")

        if score >= count / 2:
            await ctx.send(f"🎉 Tu as eu {score}/{count} bonnes réponses ! +{score} points !")
            for _ in range(score):
                update_score(str(ctx.author.id), True)
        else:
            await ctx.send(f"😢 Seulement {score}/{count} bonnes réponses. Pas de points.")
            for _ in range(count):
                update_score(str(ctx.author.id), False)

async def setup(bot):
    await bot.add_cog(AnimeQuiz(bot))

# ✅ !duel – Joue contre un ami
@commands.command(name="duel")
async def duel(ctx, opponent: discord.Member):
    if opponent.bot:
        await ctx.send("🤖 Tu ne peux pas défier un bot.")
        return
    if opponent == ctx.author:
        await ctx.send("🧍 Tu ne peux pas te défier toi-même.")
        return

    await ctx.send(f"⚔️ Duel entre {ctx.author.mention} et {opponent.mention} ! Préparez-vous...")
    data = load_json("quiz_data.json", [])
    if not data:
        await ctx.send("❌ Pas de données de quiz.")
        return

    players = [ctx.author, opponent]
    scores = {p.id: 0 for p in players}

    for i in range(3):
        q = random.choice(data)
        options = q["options"]
        correct = q["answer"]
        random.shuffle(options)
        correct_index = options.index(correct)

        embed = discord.Embed(title=f"⚔️ Duel – Question {i+1}/3", description="Quel est cet anime ?", color=discord.Color.red())
        for j, opt in enumerate(options):
            embed.add_field(name=f"{j+1}.", value=opt, inline=False)
        if q.get("image"):
            embed.set_image(url=q["image"])

        await ctx.send(embed=embed)

        def check(m): return m.author in players and m.channel == ctx.channel and m.content.isdigit()

        answered = set()
        while len(answered) < 2:
            try:
                msg = await ctx.bot.wait_for("message", check=check, timeout=15.0)
                answer = int(msg.content) - 1
                if msg.author.id in answered:
                    continue
                if answer == correct_index:
                    scores[msg.author.id] += 1
                answered.add(msg.author.id)
            except asyncio.TimeoutError:
                break
            except ValueError:
                continue

    # Résultat final
    p1, p2 = players
    s1, s2 = scores[p1.id], scores[p2.id]
    if s1 > s2:
        result = f"🏆 {p1.mention} gagne **{s1}–{s2}** ! GG !"
    elif s2 > s1:
        result = f"🏆 {p2.mention} gagne **{s2}–{s1}** ! GG !"
    else:
        result = f"🤝 Égalité parfaite **{s1}–{s2}** !"

    await ctx.send(result)

# ✅ !animebattle – Question solo rapide
@commands.command(name="animebattle")
async def anime_battle(ctx):
    await anime_quiz(ctx)

# ✅ !quiztop – Top des meilleurs
@commands.command(name="quiztop")
async def quiz_top(ctx):
    data = load_json("quiz_scores.json", {})
    if not data:
        await ctx.send("📭 Aucun score enregistré.")
        return

    sorted_scores = sorted(data.items(), key=lambda x: x[1], reverse=True)
    description = "\n".join([f"#{i+1} – <@{uid}> : {score} pts" for i, (uid, score) in enumerate(sorted_scores[:10])])
    embed = discord.Embed(title="🏆 Quiz – Top joueurs", description=description, color=discord.Color.gold())
    await ctx.send(embed=embed)

# ✅ !myrank – Ton score
@commands.command(name="myrank")
async def my_rank(ctx):
    data = load_json("quiz_scores.json", {})
    score = data.get(str(ctx.author.id), 0)
    embed = discord.Embed(
        title=f"📈 Rang de {ctx.author.display_name}",
        description=f"Tu as **{score} point{'s' if score != 1 else ''}** dans le mode quiz.",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

async def setup(bot):
    bot.add_command(anime_quiz)
    bot.add_command(anime_quiz_multi)
    bot.add_command(duel)
    bot.add_command(anime_battle)
    bot.add_command(quiz_top)
    bot.add_command(my_rank)
