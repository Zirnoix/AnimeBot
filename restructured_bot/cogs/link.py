import discord
from discord.ext import commands

from restructured_bot.modules import core

class Link(commands.Cog):
    """Cog pour lier ou délier son compte AniList."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="linkanilist")
    async def link_anilist(self, ctx: commands.Context, pseudo: str) -> None:
        """Lie votre compte AniList (pseudo) à votre profil Discord."""
        data = core.load_links()
        data[str(ctx.author.id)] = pseudo
        core.save_links(data)
        await ctx.send(f"✅ Ton compte AniList **{pseudo}** a été lié à ton profil Discord.")

    @commands.command(name="unlink")
    async def unlink(self, ctx: commands.Context) -> None:
        """Délie (supprime) le compte AniList lié à votre profil Discord."""
        data = core.load_links()
        user_id = str(ctx.author.id)
        if user_id in data:
            data.pop(user_id, None)
            core.save_links(data)
            await ctx.send("🔗 Ton lien AniList a bien été supprimé.")
        else:
            await ctx.send("❌ Aucun compte AniList n’était lié à ton profil.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Link(bot))
