# cogs/ping.py

import discord
from discord.ext import commands
from datetime import datetime

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx):
        """📶 Affiche la latence du bot"""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong ! Latence : `{latency} ms`")

    @commands.command(name="uptime")
    async def uptime(self, ctx):
        """⏱️ Affiche le temps depuis lequel le bot est en ligne"""
        now = datetime.utcnow()
        delta = now - self.bot.launch_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        await ctx.send(f"⏳ Uptime : {hours}h {minutes}min {seconds}s")

    @commands.command(name="botinfo")
    async def botinfo(self, ctx):
        """🤖 Donne des infos sur le bot"""
        embed = discord.Embed(
            title="🤖 Infos du bot",
            description="Bot animé multifonction pour les fans d'anime !",
            color=0x5865f2
        )
        embed.add_field(name="Développeur", value="Julien 🧀", inline=True)
        embed.add_field(name="Langage", value="Python 🐍", inline=True)
        embed.add_field(name="Librairie", value="discord.py", inline=True)
        embed.set_footer(text="Créé avec amour, animé avec passion ❤️")
        await ctx.send(embed=embed)

    @commands.command(name="source")
    async def source(self, ctx):
        """🔗 Lien vers le code source"""
        await ctx.send("📁 Code source : https://github.com/Zirnoix/AnimeBot")

async def setup(bot):
    await bot.add_cog(Utility(bot))
