from discord.ext import commands
import discord
from modules.utils import load_json, save_json, genre_emoji, get_user_anilist, get_user_stats, get_user_genre_chart
from io import BytesIO
import matplotlib.pyplot as plt

@commands.command(name="linkanilist")
async def link_anilist(ctx, pseudo: str = None):
    if not pseudo:
        await ctx.send("❌ Tu dois spécifier ton pseudo AniList.")
        return

    links = load_json("linked_users.json", {})
    links[str(ctx.author.id)] = pseudo
    save_json("linked_users.json", links)
    await ctx.send(f"🔗 Ton compte AniList a été lié à **{pseudo}**.")

@commands.command(name="unlink")
async def unlink_anilist(ctx):
    links = load_json("linked_users.json", {})
    if str(ctx.author.id) in links:
        del links[str(ctx.author.id)]
        save_json("linked_users.json", links)
        await ctx.send("❌ Ton lien AniList a été supprimé.")
    else:
        await ctx.send("Tu n'avais pas encore lié de compte.")

@commands.command(name="mystats")
async def mystats(ctx):
    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Aucun compte AniList lié.")
        return

    stats = get_user_stats(username)
    embed = discord.Embed(title=f"📊 Statistiques – {username}", color=discord.Color.green())
    for key, value in stats.items():
        embed.add_field(name=key, value=value, inline=True)
    await ctx.send(embed=embed)

@commands.command(name="stats")
async def stats_other(ctx, pseudo: str = None):
    if not pseudo:
        await ctx.send("❌ Donne un pseudo AniList.")
        return

    stats = get_user_stats(pseudo)
    embed = discord.Embed(title=f"📊 Statistiques – {pseudo}", color=discord.Color.green())
    for key, value in stats.items():
        embed.add_field(name=key, value=value, inline=True)
    await ctx.send(embed=embed)

@commands.command(name="mychart")
async def mychart(ctx):
    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Aucun compte AniList lié.")
        return

    genres = get_user_genre_chart(username)
    labels, sizes = zip(*genres.items())

    fig, ax = plt.subplots()
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')

    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    file = discord.File(buf, filename="chart.png")

    await ctx.send(file=file)

@commands.command(name="duelstats")
async def duelstats(ctx, member: discord.Member):
    user1 = get_user_anilist(ctx.author.id)
    user2 = get_user_anilist(member.id)
    if not user1 or not user2:
        await ctx.send("❌ Les deux utilisateurs doivent avoir lié un compte AniList.")
        return

    embed = discord.Embed(title="📊 Duel Statistiques", color=discord.Color.orange())
    embed.add_field(name=ctx.author.display_name, value=f"AniList: **{user1}**", inline=True)
    embed.add_field(name=member.display_name, value=f"AniList: **{user2}**", inline=True)
    await ctx.send(embed=embed)

async def setup(bot):
    bot.add_command(link_anilist)
    bot.add_command(unlink_anilist)
    bot.add_command(mystats)
    bot.add_command(stats_other)
    bot.add_command(mychart)
    bot.add_command(duelstats)
