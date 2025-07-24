from discord.ext import commands
import discord
from modules.utils import get_user_anilist, generate_stats_embed, generate_genre_chart
import os

@commands.command(name="linkanilist")
async def link_anilist(ctx, pseudo: str = None):
    if not pseudo:
        await ctx.send("❓ Utilise : `!linkanilist <ton_pseudo_anilist>`")
        return

    data = get_user_anilist("all")
    data[str(ctx.author.id)] = pseudo
    get_user_anilist("save", data)

    await ctx.send(f"🔗 Ton compte AniList **{pseudo}** est maintenant lié à ton profil Discord.")

@commands.command(name="unlink")
async def unlink_anilist(ctx):
    data = get_user_anilist("all")
    if str(ctx.author.id) in data:
        del data[str(ctx.author.id)]
        get_user_anilist("save", data)
        await ctx.send("❌ Ton compte AniList a été délié.")
    else:
        await ctx.send("🚫 Aucun compte lié trouvé.")

@commands.command(name="mystats")
async def mystats(ctx):
    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Utilise `!linkanilist <pseudo>` pour lier ton compte.")
        return

    embed = generate_stats_embed(username, ctx.author.display_name)
    if embed:
        await ctx.send(embed=embed)
    else:
        await ctx.send("⚠️ Impossible de récupérer les statistiques.")

@commands.command(name="stats")
async def stats(ctx, pseudo: str = None):
    if not pseudo:
        await ctx.send("❓ Utilise : `!stats <pseudo_anilist>`")
        return

    embed = generate_stats_embed(pseudo, pseudo)
    if embed:
        await ctx.send(embed=embed)
    else:
        await ctx.send("⚠️ Impossible de récupérer les statistiques pour ce pseudo.")

@commands.command(name="mychart")
@commands.command(name="monchart")
async def mychart(ctx):
    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Tu dois lier ton compte avec `!linkanilist` d'abord.")
        return

    path = generate_genre_chart(username)
    if path and os.path.exists(path):
        await ctx.send(file=discord.File(path))
        os.remove(path)
    else:
        await ctx.send("⚠️ Impossible de générer le graphique.")

async def setup(bot):
    bot.add_command(link_anilist)
    bot.add_command(unlink_anilist)
    bot.add_command(mystats)
    bot.add_command(stats)
    bot.add_command(mychart)
