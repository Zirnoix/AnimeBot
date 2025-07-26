from discord.ext import commands
import discord

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        embed = discord.Embed(title="📚 Aide des Commandes", description="Liste des commandes disponibles :", color=0x00ffcc)
        embed.add_field(name="🎮 Quiz", value="`!animequiz`, `!quiztop`, `!myrank`", inline=False)
        embed.add_field(name="❓ Aide", value="`!help`", inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))
