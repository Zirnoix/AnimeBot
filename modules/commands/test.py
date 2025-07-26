
from discord.ext import commands

@commands.command(name="ping")
async def ping(ctx):
    await ctx.send("🏓 Pong ! Le bot est en ligne.")

def setup(bot):
    bot.add_command(ping)
