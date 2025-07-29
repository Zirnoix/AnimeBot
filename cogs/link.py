import sys
sys.stdout.write("[DEBUG] cogs.link chargé\n")
sys.stdout.flush()
import discord
from discord.ext import commands
from modules.anilist import fetch_anilist_user_id
from modules.user_links import save_link, remove_link, get_link

class LinkAniList(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="linkanilist")
    async def link_anilist(self, ctx, *, username: str):
        """Lie ton compte AniList à ton compte Discord."""
        await ctx.send("🔍 Je cherche ton profil AniList, attends une seconde...")

        user_id = await fetch_anilist_user_id(username)
        if user_id:
            save_link(ctx.author.id, user_id)
            await ctx.send(f"✅ Ton compte AniList a été lié à `{username}` (ID: {user_id})")
        else:
            await ctx.send("❌ Aucun utilisateur AniList trouvé avec ce nom.")

    @commands.command(name="unlinkanilist")
    async def unlink_anilist(self, ctx):
        result = remove_link(ctx.author.id)
        if result:
            await ctx.send("✅ Ton compte AniList a été délié avec succès.")
        else:
            await ctx.send("❌ Aucun compte AniList n’est lié à ton profil Discord.")

async def setup(bot):
    await bot.add_cog(LinkAniList(bot))
