from discord.ext import commands
import discord

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='help')
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="📚 Commandes disponibles",
            description="Voici la liste des commandes que tu peux utiliser :",
            color=discord.Color.blurple()
        )

        embed.add_field(name="🎮 AnimeQuiz", value="`!animequiz` `!next` `!quiztop`", inline=False)
        embed.add_field(name="🧠 Challenge", value="`!anichallenge` `!challenge complete <note>` `!weekly`", inline=False)
        embed.add_field(name="📈 Stats", value="`!stats` `!genrestats` `!mychart`", inline=False)
        embed.add_field(name="📅 Planning", value="`!planning`", inline=False)
        embed.add_field(name="🔔 Notifications", value="`!anitracker <anime>` `!setchannel`", inline=False)
        embed.add_field(name="🔍 Recherche", value="`!search <anime>`", inline=False)
        embed.add_field(name="⚙️ Utilitaires", value="`!linkanilist <pseudo>` `!profil`", inline=False)

        embed.set_footer(text="Utilise les commandes avec le préfixe `!`")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCommand(bot))

