from discord.ext import commands
import discord
from modules.utils import get_user_anilist, generate_stats_embed, generate_genre_chart, get_user_genres
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

@commands.command(name="genrestats")
async def genre_stats(ctx):
    user_id = str(ctx.author.id)
    genres = get_user_genres(user_id)

    if not genres:
        await ctx.send("😕 Je n’ai trouvé aucun genre pour toi. Essaie d’abord de synchroniser ton profil.")
        return

    genre_counts = Counter(genres)
    top_genres = genre_counts.most_common(8)

    labels, values = zip(*top_genres)

    # 🌈 Création du graph fun et coloré
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.barh(labels, values)
    ax.set_title(f"Tes genres d'anime préférés", fontsize=16, fontweight='bold')
    ax.invert_yaxis()

    # Couleurs dynamiques
    for bar in bars:
        bar.set_color(plt.cm.cool_r(np.random.rand()))

    plt.tight_layout()
    path = f"genre_chart_{ctx.author.id}.png"
    plt.savefig(path, transparent=True)
    plt.close()

    embed = discord.Embed(
        title="📊 Tes stats de genres anime",
        description="Voici une vue stylée de tes préférences ! ✨",
        color=discord.Color.magenta()
    )
    embed.set_image(url=f"attachment://{os.path.basename(path)}")

    await ctx.send(embed=embed, file=discord.File(path))
    os.remove(path)

async def setup(bot):
    bot.add_command(link_anilist)
    bot.add_command(unlink_anilist)
    bot.add_command(mystats)
    bot.add_command(stats)
    bot.add_command(genre_stats)
