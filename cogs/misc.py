import discord
from discord.ext import commands
import datetime
import time

class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.command(name="ping")
    async def ping(self, ctx):
        await ctx.send("🏓 Pong !")

    @commands.command(name="botinfo")
    async def botinfo(self, ctx):
        embed = discord.Embed(title="📌 Informations sur le bot", color=0x5865F2)
        embed.add_field(name="Développeur", value="Zirnoix", inline=True)
        embed.add_field(name="Librairie", value="discord.py", inline=True)
        embed.add_field(name="Langage", value="Python 3.11+", inline=True)
        embed.set_footer(text="AnimeBot - par Zirnoix")
        await ctx.send(embed=embed)

    @commands.command(name="source")
    async def source(self, ctx):
        await ctx.send("💡 Code source disponible ici : https://github.com/Zirnoix/AnimeBot")

    @commands.command(name="uptime")
    async def uptime(self, ctx):
        uptime_seconds = int(time.time() - self.start_time)
        uptime_str = str(datetime.timedelta(seconds=uptime_seconds))
        await ctx.send(f"🕒 Uptime : {uptime_str}")

    @commands.command(name="todayinhistory")
    async def today_in_history(self, ctx):
        today = datetime.datetime.now().strftime("%m-%d")
        # Exemple d’anecdote (à remplacer avec une vraie base de données ou API plus tard)
        mock_history = {
            "07-27": ["✨ 2002 : Diffusion de l’épisode final de *Naruto* au Japon.",
                      "📚 1995 : Sortie du manga *Great Teacher Onizuka*."],
            "12-25": ["🎄 Joyeux Noël ! Peu d’animes diffusés ce jour-là."]
        }

        facts = mock_history.get(today, [])
        if not facts:
            await ctx.send("📭 Aucune info historique disponible pour aujourd’hui.")
            return

        embed = discord.Embed(title="📅 Aujourd’hui dans l’histoire de l’anime", color=0xe67e22)
        for fact in facts:
            embed.add_field(name="", value=fact, inline=False)

        embed.set_footer(text="AnimeBot - Culture animée")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Misc(bot))
