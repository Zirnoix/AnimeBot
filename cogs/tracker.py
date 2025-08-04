# cogs/tracker.py

import discord
from discord.ext import commands
from modules.scheduler import schedule_daily_task
from modules.channel_config import save_configured_channel_id, remove_configured_channel_id

class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setchannel")
    @commands.has_permissions(manage_guild=True)
    async def set_channel(self, ctx):
        """🔔 Définit ce salon pour recevoir les notifications quotidiennes d’épisodes"""
        guild = ctx.guild
        channel_id = ctx.channel.id

        save_configured_channel_id(str(guild.id), channel_id)
        schedule_daily_task(self.bot, guild, callback=None)  # le callback est défini dans scheduler
        await ctx.send("✅ Ce salon recevra désormais les notifications des épisodes du jour à 08h.")

    @commands.command(name="disablechannel")
    @commands.has_permissions(manage_guild=True)
    async def disable_channel(self, ctx):
        """🚫 Désactive les notifications dans ce salon"""
        remove_configured_channel_id(str(ctx.guild.id))
        await ctx.send("❌ Notifications automatiques désactivées pour ce serveur.")

async def setup(bot):
    await bot.add_cog(Tracker(bot))
