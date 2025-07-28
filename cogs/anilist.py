import discord
from discord.ext import commands
from modules.anilist import fetch_user_profile
import json
import os

LINKS_FILE = "data/user_links.json"

class AniListProfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_linked_anilist_id(self, discord_id):
        if not os.path.exists(LINKS_FILE):
            return None
        with open(LINKS_FILE, "r") as f:
            data = json.load(f)
        return data.get(str(discord_id), None)

    @commands.command(name="anilist")
    async def anilist(self, ctx):
        """Affiche ton profil AniList lié."""
        user_id = self.get_linked_anilist_id(ctx.author.id)
        if not user_id:
            await ctx.send("❌ Tu n’as pas encore lié ton compte AniList avec `!linkanilist <pseudo>`.")
            return

        user = await fetch_user_profile(ctx.author.name)
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
