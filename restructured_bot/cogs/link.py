# restructured_bot/cogs/link.py

import discord
from discord.ext import commands
from restructured_bot.modules import core, database, anilist

class AniListLink(commands.Cog):
    """Commandes pour lier ou délier son compte AniList."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="linkanilist")
    async def link_anilist(self, ctx: commands.Context, *, username: str):
        """Lie votre compte AniList à votre compte Discord."""
        user_id = str(ctx.author.id)
        user_data = anilist.query_anilist(username)

        if not user_data:
            await ctx.send("❌ Nom d’utilisateur AniList invalide ou introuvable.")
            return

        database.save_anilist_link(user_id, user_data["id"], user_data["name"])
        await ctx.send(f"✅ Compte AniList **{user_data['name']}** lié avec succès à {ctx.author.mention}.")

    @commands.command(name="unlinkanilist")
    async def unlink_anilist(self, ctx: commands.Context):
        """Délie votre compte AniList de votre compte Discord."""
        user_id = str(ctx.author.id)
        if database.remove_anilist_link(user_id):
            await ctx.send(f"🔗 Le lien avec votre compte AniList a été supprimé.")
        else:
            await ctx.send("❌ Aucun compte AniList n’est actuellement lié à votre profil.")

async def setup(bot: commands.Bot):
    await bot.add_cog(AniListLink(bot))
