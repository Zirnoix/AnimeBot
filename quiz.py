from discord.ext import commands
import discord
from modules.utils import *


from discord.ext import commands
import discord
import random
from modules.utils import load_json, save_json, genre_emoji

@commands.command(name="animequiz")
async def anime_quiz(ctx):
    await ctx.send("🎯 Commande animequiz en cours de construction...")

@commands.command(name="animequizmulti")
async def anime_quiz_multi(ctx, nombre: int = 5):
    await ctx.send(f"🔢 Commande animequizmulti avec {nombre} questions...")

@commands.command(name="duel")
async def duel(ctx, opponent: discord.Member):
    await ctx.send(f"⚔️ Duel entre {ctx.author.display_name} et {opponent.display_name}...")

@commands.command(name="quiztop")
async def quiz_top(ctx):
    data = load_json("quiz_scores.json", {})
    sorted_scores = sorted(data.items(), key=lambda x: x[1], reverse=True)
    description = "\n".join([f"#{i+1} – {user}: {score} pts" for i, (user, score) in enumerate(sorted_scores[:10])])
    embed = discord.Embed(title="🏆 Quiz – Top joueurs", description=description, color=discord.Color.gold())
    await ctx.send(embed=embed)

@commands.command(name="myrank")
async def my_rank(ctx):
    data = load_json("quiz_scores.json", {})
    score = data.get(str(ctx.author.id), 0)
    embed = discord.Embed(
        title=f"📈 Rang de {ctx.author.display_name}",
        description=f"Tu as **{score} points** dans le mode quiz.",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

@commands.command(name="animebattle")
async def anime_battle(ctx):
    await ctx.send("⚡ Mode animebattle lancé ! Une question rapide incoming...")


def setup(bot):
    bot.add_command(anime_quiz)
    bot.add_command(anime_quiz_multi)
    bot.add_command(duel)
    bot.add_command(quiz_top)
    bot.add_command(my_rank)
    bot.add_command(anime_battle)
