# cogs/help.py

import discord
from discord.ext import commands
from discord.ext.commands import CommandNotFound

class CustomHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.remove_command("help")  # Supprime la commande par défaut

    @commands.command(name="help")
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="📚 Menu d'Aide",
            description="Voici la liste des commandes disponibles :",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="🎮 Quiz & Mini-jeux",
            value="`!animequiz`, `!guessyear`, `!guessgenre`, `!guessepisode`, `!guesscharacter`, `!guessop`",
            inline=False
        )
        embed.add_field(
            name="📊 Statistiques & Profil",
            value="`!myrank`, `!mycard`, `!stats`, `!quiztop`",
            inline=False
        )
        embed.add_field(
            name="📅 Planning & Notifications",
            value="`!planning`, `!next`, `!monnext`, `!track`, `!untrack`",
            inline=False
        )
        embed.add_field(
            name="🔗 AniList",
            value="`!linkanilist`, `!unlinkanilist`, `!anilist`, `!duel`",
            inline=False
        )
        embed.add_field(
            name="⚙️ Utilitaires",
            value="`!ping`, `!botinfo`, `!uptime`, `!source`, `!help`",
            inline=False
        )
        embed.set_footer(text="AnimeBot • Parlez à un admin si vous avez un souci avec une commande.")
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else discord.Embed.Empty)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CustomHelp(bot))
