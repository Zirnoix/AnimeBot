from discord.ext import commands
from modules import core

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="updatecache")
    @commands.is_owner()
    async def update_cache_command(self, ctx):
        await ctx.send("🔄 Mise à jour du cache AniList en cours…")
        anime_list = core.fetch_balanced_anime_cache()
        await ctx.send(f"✅ Cache mis à jour avec {len(anime_list)} animés.")

async def setup(bot):
    await bot.add_cog(Admin(bot))
