from discord.ext import commands
import discord
from modules.utils import get_all_user_genres, genre_emoji

@commands.command(name="classementgenre")
async def classement_genre(ctx, *, genre: str):
    genre = genre.title()
    data = get_all_user_genres()

    top_users = []
    for user_id, genres in data.items():
        count = genres.get(genre, 0)
        if count > 0:
            top_users.append((user_id, count))

    if not top_users:
        await ctx.send(f"❌ Aucun utilisateur trouvé avec des animés dans le genre `{genre}`.")
        return

    top_users.sort(key=lambda x: x[1], reverse=True)
    description = "\n".join([
        f"#{i+1} – <@{uid}> : {count} animés"
        for i, (uid, count) in enumerate(top_users[:10])
    ])
    emoji = genre_emoji([genre]) or "📊"
    embed = discord.Embed(
        title=f"{emoji} Classement – {genre}",
        description=description,
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)

async def setup(bot):
    bot.add_command(classement_genre)
