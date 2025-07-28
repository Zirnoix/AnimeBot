import asyncio
import datetime
import discord

from discord.ext import tasks
from modules.anilist import get_upcoming_episodes
from modules.channel_config import get_alert_channel
from modules.user_settings import load_user_settings

class Scheduler:
    def __init__(self, bot):
        self.bot = bot
        self.alerted = set()
        self.check_airing_episodes.start()

    @tasks.loop(minutes=5)
    async def check_airing_episodes(self):
        await self.bot.wait_until_ready()
        user_links = load_user_settings()

        for user_id, anilist_username in user_links.items():
            upcoming = get_upcoming_episodes(anilist_username)
            for ep in upcoming:
                airing_time = datetime.datetime.fromtimestamp(ep["airingAt"])
                now = datetime.datetime.now()
                delta = airing_time - now

                if 0 < delta.total_seconds() <= 1800:  # Moins de 30 minutes
                    key = f"{anilist_username}_{ep['title']}_{ep['episode']}"
                    if key in self.alerted:
                        continue

                    self.alerted.add(key)
                    channel_id = get_alert_channel(user_id)
                    if not channel_id:
                        continue

                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        embed = discord.Embed(
                            title=f"⏰ Nouvel épisode bientôt !",
                            description=f"L’épisode **{ep['episode']}** de **{ep['title']}** sort dans moins de 30 minutes !",
                            color=0xffc107
                        )
                        embed.set_footer(text="AnimeBot - Alerte de sortie")
                        await channel.send(embed=embed)

    @check_airing_episodes.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    def stop(self):
        self.check_airing_episodes.cancel()
