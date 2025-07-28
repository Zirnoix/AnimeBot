import discord
from discord.ext import commands
from modules.anilist import get_next_episode_for_user, get_next_airing_episodes
from modules.user_settings import get_anilist_username
from datetime import datetime
import time

class Episodes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="next")
    async def next_episode(self, ctx):
        ep = get_next_episode_for_user("Zirnoix")  # Utilisateur par défaut codé en dur
        if not ep:
            await ctx.send("📭 Aucun épisode à venir trouvé.")
            return

        ts = time.strftime('%d/%m/%Y %H:%M', time.localtime(ep['airingAt']))
        await ctx.send(f"🎬 Prochain épisode de **{ep['title']}**: épisode **{ep['episode']}** à **{ts}**.")

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
        await ctx.send(f"🎬 Prochain épisode de **{ep['title']}**: épisode **{ep['episode']}** à **{ts}**.")

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

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Episodes(bot))
