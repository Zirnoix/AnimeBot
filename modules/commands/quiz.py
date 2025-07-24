from discord.ext import commands
import discord
import random
import asyncio
from modules.utils import load_json, save_json

# ✅ !animequiz – Devine 1 anime
@commands.command(name="animequiz")
async def anime_quiz(ctx):
    data = load_json("quiz_data.json", [])
    if not data:
        await ctx.send("❌ Aucune question disponible.")
        return

    question = random.choice(data)
    anime = question["anime"]
    options = question["options"]
    correct = question["answer"]

    random.shuffle(options)
    correct_index = options.index(correct)

    embed = discord.Embed(
        title="🎮 Anime Quiz",
        description="Quel est cet anime ?",
        color=discord.Color.blurple()
    )
    for i, opt in enumerate(options):
        embed.add_field(name=f"{i+1}.", value=opt, inline=False)
    if question.get("image"):
        embed.set_image(url=question["image"])

    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

    try:
        guess = await ctx.bot.wait_for("message", check=check, timeout=15.0)
        user_answer = int(guess.content) - 1
    except asyncio.TimeoutError:
        await ctx.send(f"⏱️ Temps écoulé ! La bonne réponse était : **{correct}**")
        return
    except ValueError:
        await ctx.send("❌ Réponse invalide.")
        return

    if user_answer == correct_index:
        await ctx.send("✅ Bonne réponse !")
        scores = load_json("quiz_scores.json", {})
        uid = str(ctx.author.id)
        scores[uid] = scores.get(uid, 0) + 1
        save_json("quiz_scores.json", scores)
    else:
        await ctx.send(f"❌ Mauvaise réponse. C'était **{correct}**.")

# ✅ !animequizmulti – N questions de suite
@commands.command(name="animequizmulti")
async def anime_quiz_multi(ctx, nombre: int = 5):
    data = load_json("quiz_data.json", [])
    if not data or nombre < 1:
        await ctx.send("❌ Pas assez de données ou nombre invalide.")
        return

    score = 0
    used = []

    for i in range(nombre):
        question = random.choice([q for q in data if q not in used])
        used.append(question)
        options = question["options"]
        correct = question["answer"]
        random.shuffle(options)
        correct_index = options.index(correct)

        embed = discord.Embed(
            title=f"Question {i+1}/{nombre}",
            description="Quel est cet anime ?",
            color=discord.Color.blurple()
        )
        for j, opt in enumerate(options):
            embed.add_field(name=f"{j+1}.", value=opt, inline=False)
        if question.get("image"):
            embed.set_image(url=question["image"])
        await ctx.send(embed=embed)

        def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            guess = await ctx.bot.wait_for("message", check=check, timeout=15.0)
            user_answer = int(guess.content) - 1
        except asyncio.TimeoutError:
            await ctx.send(f"⏱️ Temps écoulé ! Réponse : **{correct}**")
            continue
        except ValueError:
            await ctx.send("❌ Réponse invalide.")
            continue

        if user_answer == correct_index:
            await ctx.send("✅ Bonne réponse !")
            score += 1
        else:
            await ctx.send(f"❌ Faux. Réponse : **{correct}**")

    await ctx.send(f"🏁 Fin du quiz ! Score : **{score}/{nombre}**")

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
