# modules/scheduler.py

import asyncio
from datetime import datetime, timedelta
from discord.ext import tasks
from modules.history_data import get_today_anime_data
from modules.channel_config import get_configured_channel_id
from modules.anilist import get_next_airing_anime

scheduled_tasks = {}

def schedule_daily_task(bot, guild, callback):
    guild_id = str(guild.id)
    if guild_id in scheduled_tasks:
        return  # Already scheduled

    @tasks.loop(hours=24)
    async def daily_task():
        now = datetime.now()
        if now.hour != 8:
            return  # Envoie seulement à 08h du matin

        channel_id = get_configured_channel_id(guild_id)
        if not channel_id:
            return

        channel = bot.get_channel(channel_id)
        if channel:
            await callback(channel)

    @daily_task.before_loop
    async def before():
        await bot.wait_until_ready()
        now = datetime.now()
        next_run = datetime.combine(now.date(), datetime.min.time()) + timedelta(days=1, hours=8)
        wait_time = (next_run - now).total_seconds()
        await asyncio.sleep(max(wait_time, 0))

    daily_task.start()
    scheduled_tasks[guild_id] = daily_task

async def send_today_planning(channel):
    today = datetime.now().strftime("%Y-%m-%d")
    anime_data = get_today_anime_data(today)
    
    if not anime_data:
        await channel.send("📭 Aucun épisode prévu aujourd’hui.")
        return

    lines = []
    for anime in anime_data:
        lines.append(f"📺 **{anime['title']}** — Épisode **{anime['episode']}**")

    embed_content = "\n".join(lines)
    await channel.send(embed=discord.Embed(
        title="🗓️ Planning du jour",
        description=embed_content,
        color=0x00acee
    ))

async def send_next_airing(channel):
    embed = await get_next_airing_anime()
    if embed:
        await channel.send(embed=embed)
    else:
        await channel.send("❌ Impossible de récupérer le prochain épisode.")
