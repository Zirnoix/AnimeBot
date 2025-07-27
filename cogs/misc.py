import discord
from discord.ext import commands
import datetime
import psutil
import time

start_time = time.time()

class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="uptime")
    async def uptime(self, ctx):
        uptime_seconds = int(time.time() - start_time)
        uptime_str = str(datetime.timedelta(seconds=uptime_seconds))
        await ctx.send(f"🕒 Uptime : `{uptime_str}`")

    @commands.command(name="todayinhistory")
    async def todayinhistory(self, ctx):
        today = datetime.datetime.now()
        date_str = today.strftime("%d %B")
        await ctx.send(f"📜 Aujourd’hui dans l’histoire ({date_str}) : Cette fonction est encore en développement.")

async def setup(bot):
    await bot.add_cog(Misc(bot))
