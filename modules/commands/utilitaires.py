from discord.ext import commands
import discord
import time
from modules.utils import load_json, save_json

bot_start_time = time.time()

@commands.command(name="uptime")
async def uptime(ctx):
    seconds = int(time.time() - bot_start_time)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    await ctx.send(f"⏱️ Uptime : {hours}h {minutes}m {seconds}s")

@commands.command(name="setnotifchannel")
async def set_channel(ctx):
    data = load_json("preferences.json", {})
    data["notification_channel"] = ctx.channel.id
    save_json("preferences.json", data)
    await ctx.send("✅ Ce salon a été défini comme canal des notifications.")

@commands.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge(ctx, nombre: int = 10):
    await ctx.channel.purge(limit=nombre + 1)
    confirmation = await ctx.send(f"🧹 {nombre} messages supprimés.")
    await confirmation.delete(delay=5)

async def setup(bot):
    bot.add_command(uptime)
    bot.add_command(set_channel)
    bot.add_command(purge)
