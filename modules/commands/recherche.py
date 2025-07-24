from discord.ext import commands
import discord
from modules.utils import search_anime, get_top_animes, get_seasonal_animes

@commands.command(name="search")
async def search(ctx, *, query):
    result = search_anime(query)
    if not result:
        await ctx.send("❌ Aucun anime trouvé.")
        return

    embed = discord.Embed(
        title=result["title"],
        description=result["description"][:500] + "...",
        color=discord.Color.green(),
        url=result["url"]
    )
    embed.set_image(url=result["image"])
    await ctx.send(embed=embed)

@commands.command(name="topanime")
async def top_anime(ctx):
    animes = get_top_animes()
    description = "\n".join([f"#{i+1} – {a['title']} ({a['score']}/100)" for i, a in enumerate(animes[:10])])
    embed = discord.Embed(title="🏆 Top 10 des animés", description=description, color=discord.Color.gold())
    await ctx.send(embed=embed)

@commands.command(name="seasonal")
async def seasonal(ctx):
    animes = get_seasonal_animes()
    description = "\n".join([f"• {a['title']} ({a['score']}/100)" for a in animes[:10]])
    embed = discord.Embed(title="📅 Animés de la saison", description=description, color=discord.Color.blurple())
    await ctx.send(embed=embed)

async def setup(bot):
    bot.add_command(search)
    bot.add_command(top_anime)
    bot.add_command(seasonal)
