import discord
from discord.ext import commands
import random
import asyncio
from modules.utils import (
    load_json, save_json, normalize_title,
    get_anilist_user_animelist, get_anime_list, update_score
)

class AnimeQuiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.anime_list = get_anime_list()

    @commands.command(name="animequizmulti")
    async def animequizmulti(self, ctx, count: int = 10):
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

    @commands.command(name="animequiz")
    async def animequiz(self, ctx):
        anime = random.choice(get_anime_list())
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

    @commands.command(name="duel")
    async def duel(self, ctx, opponent: discord.Member):
        if opponent.bot:
            return await ctx.send("🤖 Tu ne peux pas défier un bot.")
        if opponent == ctx.author:
            return await ctx.send("🧍 Tu ne peux pas te défier toi-même.")

        await ctx.send(f"⚔️ Duel entre {ctx.author.mention} et {opponent.mention} ! Préparez-vous...")

        data = load_json("quiz_data.json", [])
        if not data:
            return await ctx.send("❌ Pas de données de quiz.")

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
                    msg = await self.bot.wait_for("message", check=check, timeout=15.0)
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

        p1, p2 = players
        s1, s2 = scores[p1.id], scores[p2.id]
        if s1 > s2:
            result = f"🏆 {p1.mention} gagne **{s1}–{s2}** ! GG !"
        elif s2 > s1:
            result = f"🏆 {p2.mention} gagne **{s2}–{s1}** ! GG !"
        else:
            result = f"🤝 Égalité parfaite **{s1}–{s2}** !"

        await ctx.send(result)

    @commands.command(name="animebattle")
    async def anime_battle(self, ctx):
        anime = random.choice(self.anime_list)
        await ctx.send(f"🎲 Quel est cet anime ? `{normalize_title(anime)}`")

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

    @commands.command(name="quiztop")
    async def quiz_top(self, ctx):
        data = load_json("quiz_scores.json", {})
        if not data:
            return await ctx.send("📭 Aucun score enregistré.")

        sorted_scores = sorted(data.items(), key=lambda x: x[1], reverse=True)
        description = "\n".join([f"#{i+1} – <@{uid}> : {score} pts" for i, (uid, score) in enumerate(sorted_scores[:10])])
        embed = discord.Embed(title="🏆 Quiz – Top joueurs", description=description, color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def my_rank(self, ctx):
        data = load_json("quiz_scores.json", {})
        score = data.get(str(ctx.author.id), 0)
        embed = discord.Embed(
            title=f"📈 Rang de {ctx.author.display_name}",
            description=f"Tu as **{score} point{'s' if score != 1 else ''}** dans le mode quiz.",
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)

# Le bon setup, à garder en bas du fichier
async def setup(bot):
    await bot.add_cog(AnimeQuiz(bot))
