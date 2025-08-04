import discord
from discord.ext import commands
from modules import user_settings, anilist

class AniListCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="linkanilist")
    async def link_anilist(self, ctx, *, username: str = None):
        if not username:
            await ctx.send("❗ Utilisation : `!linkanilist <nom_anilist>`")
            return

        user_settings.set_anilist_username(ctx.author.id, username)
        await ctx.send(f"✅ Compte AniList lié à **{username}**.")

    @commands.command(name="unlinkanilist")
    async def unlink_anilist(self, ctx):
        removed = user_settings.remove_anilist_username(ctx.author.id)
        if removed:
            await ctx.send("🗑️ Compte AniList délié avec succès.")
        else:
            await ctx.send("⚠️ Aucun compte AniList n'était lié.")

    @commands.command(name="anilist")
    async def anilist_profile(self, ctx, user: discord.User = None):
        target = user or ctx.author
        user_id = str(target.id)

        username = user_settings.get_anilist_username(user_id)
        if not username:
            await ctx.send("❌ Cet utilisateur n’a pas encore lié son compte AniList.")
            return

        data = anilist.get_user_profile(username)
        if not data:
            await ctx.send("❌ Impossible de récupérer les données du profil.")
            return

        stats = data["statistics"]["anime"]
        embed = discord.Embed(
            title=f"📊 Profil AniList — {username}",
            url=f"https://anilist.co/user/{username}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=data["avatar"]["large"])
        embed.add_field(name="📺 Animes vus", value=stats["count"])
        embed.add_field(name="⏱️ Temps total", value=f'{round(stats["minutesWatched"] / 60, 1)}h')
        embed.add_field(name="⭐ Note moyenne", value=stats["meanScore"])
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AniListCog(bot))
