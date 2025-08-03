import discord
from discord.ext import commands
from datetime import datetime
import restructured_bot.modules.core as core
import restructured_bot.modules.anilist as anilist
import restructured_bot.modules.database as db

class Episodes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="next")
    async def next_episode(self, ctx):
        """Prochain épisode depuis TON AniList (config par défaut)"""
        airing = anilist.get_next_airing()
        if not airing:
            await ctx.send("❌ Aucun épisode à venir trouvé.")
            return
        now = datetime.now(tz=core.TIMEZONE)
        buf = core.generate_next_image(airing, now)
        if not buf:
            await ctx.send("❌ Impossible de générer l’image.")
            return
        await ctx.send(file=discord.File(buf, filename="next.jpg"))

    @commands.command(name="monnext")
    async def user_next_episode(self, ctx):
        """Prochain épisode pour l’utilisateur (si AniList lié)"""
        user_id = str(ctx.author.id)
        linked = db.get_linked_anilist(user_id)
        if not linked:
            await ctx.send("❌ Tu n’as pas lié ton compte AniList. Utilise `!linkanilist`.")
            return
        airing = anilist.get_next_airing(linked)
        if not airing:
            await ctx.send("❌ Aucun épisode à venir trouvé pour ton compte.")
            return
        now = datetime.now(tz=core.TIMEZONE)
        buf = core.generate_next_image(airing, now)
        if not buf:
            await ctx.send("❌ Impossible de générer l’image.")
            return
        await ctx.send(file=discord.File(buf, filename="monnext.jpg"))

    @commands.command(name="planning")
    async def weekly_schedule(self, ctx):
        """Planning des épisodes de la semaine depuis TON AniList"""
        episodes = anilist.get_upcoming_episodes()
        if not episodes:
            await ctx.send("❌ Aucun épisode prévu cette semaine.")
            return

        embed = discord.Embed(
            title="📅 Planning des épisodes à venir",
            description="Voici les prochains épisodes à venir cette semaine.",
            color=discord.Color.blurple(),
        )
        for ep in episodes[:10]:  # limite d’affichage
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            genre_emoji = core.genre_emoji(ep.get("genres", []))
            embed.add_field(
                name=f"{genre_emoji} {ep['title']} – Épisode {ep['episode']}",
                value=f"🕒 {dt.strftime('%A %d %B à %Hh%M')}",
                inline=False
            )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Episodes(bot))
