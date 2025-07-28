import discord
from discord.ext import commands
from modules.anilist import get_next_episode_for_user, get_next_airing_episodes
from modules.user_settings import get_anilist_username
import time

class Episodes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="next")
    async def next_episode(self, ctx):
        ep = get_next_episode_for_user("Zirnoix")
        if not ep:
            await ctx.send("📭 Aucun épisode à venir trouvé.")
            return

        ts = time.strftime('%d/%m/%Y %H:%M', time.localtime(ep['airingAt']))
        embed = discord.Embed(title="🎬 Prochain épisode", color=0x3498db)
        embed.add_field(name=ep['title'], value=f"Épisode **{ep['episode']}** à **{ts}**", inline=False)
        embed.set_footer(text="AnimeBot - Anilist Tracker")
        await ctx.send(embed=embed)

    @commands.command(name="monnext")
    async def my_next(self, ctx):
        username = get_anilist_username(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu dois lier ton compte Anilist avec `!linkanilist <pseudo>`.")
            return

        ep = get_next_episode_for_user(username)
        if not ep:
            await ctx.send("📭 Aucun épisode à venir trouvé.")
            return

        ts = time.strftime('%d/%m/%Y %H:%M', time.localtime(ep['airingAt']))
        embed = discord.Embed(title="🎬 Prochain épisode personnel", color=0x9b59b6)
        embed.add_field(name=ep['title'], value=f"Épisode **{ep['episode']}** à **{ts}**", inline=False)
        embed.set_footer(text=f"AnimeBot - pour {username}")
        await ctx.send(embed=embed)

    @commands.command(name="prochains")
    async def all_next(self, ctx):
        username = get_anilist_username(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu dois lier ton compte Anilist avec `!linkanilist <pseudo>`.")
            return

        airing = get_next_airing_episodes(username)
        if not airing:
            await ctx.send("📭 Aucun épisode à venir trouvé.")
            return

        embed = discord.Embed(title=f"🍿 Prochains épisodes de {username}", color=0x1abc9c)
        for anime in airing[:10]:
            ts = time.strftime('%d/%m/%Y %H:%M', time.localtime(anime['airingAt']))
            embed.add_field(name=anime['title'], value=f"Épisode {anime['episode']} à {ts}", inline=False)

        embed.set_footer(text="AnimeBot - Calendrier des sorties")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Episodes(bot))
