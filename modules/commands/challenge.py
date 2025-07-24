from discord.ext import commands
import discord
from datetime import datetime
from modules.utils import load_json, save_json

@commands.command(name="anichallenge")
async def anichallenge(ctx):
    challenges = load_json("anichallenges.json", [])
    if not challenges:
        await ctx.send("❌ Aucun challenge n'est disponible actuellement.")
        return

    users = load_json("user_challenges.json", {})
    user_id = str(ctx.author.id)

    if user_id in users:
        await ctx.send("🕒 Tu as déjà un challenge en cours ! Termine-le avant d'en prendre un autre.")
        return

    challenge = random.choice(challenges)
    users[user_id] = {
        "anime": challenge,
        "completed": False,
        "timestamp": datetime.now().isoformat()
    }
    save_json("user_challenges.json", users)

    embed = discord.Embed(
        title="🎯 Ton défi anime",
        description=f"Regarde : **{challenge}**
Quand tu as fini, tape `!challenge complete <note>` pour le valider.",
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)

@commands.command(name="challenge")
async def challenge_complete(ctx, action=None, *, note=None):
    if action != "complete" or note is None:
        await ctx.send("❓ Utilisation : `!challenge complete <note sur 10>`")
        return

    users = load_json("user_challenges.json", {})
    user_id = str(ctx.author.id)

    if user_id not in users:
        await ctx.send("🚫 Tu n’as pas encore de défi en cours.")
        return

    user_challenge = users.pop(user_id)
    save_json("user_challenges.json", users)

    archive = load_json("challenge_history.json", [])
    archive.append({
        "user": user_id,
        "anime": user_challenge["anime"],
        "note": note,
        "date": datetime.now().isoformat()
    })
    save_json("challenge_history.json", archive)

    await ctx.send(f"✅ Challenge terminé ! Tu as noté **{user_challenge['anime']}** : {note}/10")

@commands.command(name="weekly")
async def weekly(ctx):
    data = load_json("weekly_challenge.json", {})
    if not data:
        await ctx.send("📭 Aucun défi hebdomadaire défini.")
        return

    embed = discord.Embed(
        title="📆 Défi hebdomadaire",
        description=f"Anime à regarder : **{data.get('anime', '???')}**",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Utilise `!weekly complete` quand tu l’as vu.")
    await ctx.send(embed=embed)

@commands.command(name="weekly_complete")
async def weekly_complete(ctx):
    completed = load_json("weekly_done.json", {})
    user_id = str(ctx.author.id)

    if user_id in completed:
        await ctx.send("✅ Tu as déjà complété le défi hebdomadaire cette semaine.")
        return

    completed[user_id] = datetime.now().isoformat()
    save_json("weekly_done.json", completed)

    await ctx.send("🎉 Bien joué ! Tu as terminé le défi hebdo !")

async def setup(bot):
    bot.add_command(anichallenge)
    bot.add_command(challenge_complete)
    bot.add_command(weekly)
    bot.add_command(weekly_complete)
