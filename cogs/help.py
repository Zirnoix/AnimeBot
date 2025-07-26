from discord.ext import commands
import discord

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        embed = discord.Embed(title="📚 Commandes du bot", description="Voici la liste des commandes disponibles :", color=0x1abc9c)
        embed.add_field(name="🎮 Quiz", value="`!animequiz`, `!quiztop`, `!myrank`", inline=False)
        embed.add_field(name="🛠️ Autres", value="`!help`, etc.", inline=False)
        embed.set_footer(text="Utilise les commandes pour en savoir plus !")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))
