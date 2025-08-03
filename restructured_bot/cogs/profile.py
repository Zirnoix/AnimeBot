# restructured_bot/cogs/profile.py

import discord
from discord.ext import commands
from restructured_bot.modules import core, xp_manager, image

class UserProfile(commands.Cog):
    """Affiche la carte de profil d’un utilisateur avec son niveau et XP."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="mycard")
    async def mycard(self, ctx: commands.Context):
        """Affiche votre profil (niveau, XP, rang) sous forme d’image."""
        user_id = str(ctx.author.id)
        xp_data = xp_manager.load_levels()
        user_data = xp_data.get(user_id)

        if not user_data:
            await ctx.send("❌ Vous n’avez pas encore de profil. Participez un peu pour en générer un !")
            return

        level = user_data.get("level", 1)
        xp = user_data.get("xp", 0)
        rank = core.get_user_rank(user_id, xp_data)

        buf = image.generate_profile_card(ctx.author.name, level, xp, rank)
        if buf is None:
            await ctx.send("❌ Une erreur est survenue lors de la génération de la carte.")
            return

        await ctx.send(file=discord.File(buf, filename="mycard.jpg"))

async def setup(bot: commands.Bot):
    await bot.add_cog(UserProfile(bot))
