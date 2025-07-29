import sys
sys.stdout.write("[DEBUG] cogs.anilist chargé\n")
sys.stdout.flush()
import discord
from discord.ext import commands
from modules.anilist import fetch_user_profile_by_id
from modules.user_links import get_link

class AniListProfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="anilist")
    async def anilist(self, ctx):
        """Affiche ton profil AniList lié."""
        print(f"[DEBUG] !anilist lancé par {ctx.author.name} ({ctx.author.id})")

        user_id = get_link(ctx.author.id)
        print(f"[DEBUG] ID AniList trouvé en base : {user_id}")

        if not user_id:
            await ctx.send("❌ Tu n’as pas encore lié ton compte AniList avec `!linkanilist <pseudo>`.")
            return

        user = await fetch_user_profile_by_id(user_id)
        if not user:
            await ctx.send("❌ Impossible de récupérer les infos de ton compte AniList.")
            return

        stats = user.get("statistics", {}).get("anime", {})
        embed = discord.Embed(
            title=f"Profil AniList de {user['name']}",
            url=user["siteUrl"],
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=user["avatar"]["large"])
        embed.add_field(name="📺 Animes vus", value=stats.get("count", 0))
        embed.add_field(name="⭐ Score moyen", value=round(stats.get("meanScore", 0), 2))
        embed.add_field(name="🕒 Minutes regardées", value=stats.get("minutesWatched", 0))
        embed.set_footer(text="Données récupérées depuis AniList")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AniListProfile(bot))
