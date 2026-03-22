from __future__ import annotations
import asyncio, os
from discord.ext import commands, tasks
from modules import core

class AniListSync(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        hours = int(os.getenv("ANILIST_TTL_HOURS", "2"))
        # on démarre à l'intervalle courant, mais on peut changer dynamiquement
        self.sync_all.change_interval(hours=hours)
        self.sync_all.start()

    def cog_unload(self):
        self.sync_all.cancel()

    @tasks.loop(hours=2)
    async def sync_all(self):
        names = core.get_linked_anilist_usernames_bulk()
        for name in names:
            try:
                core.get_profile_stats(name, force=True)
                core.get_list_total_entries(name, force=True)
                core.get_upcoming_episodes(name, force=True)
            except Exception as e:
                print(f"[AniListSync] {name}: {e}")
            await asyncio.sleep(1.0)  # anti rate-limit

async def setup(bot: commands.Bot):
    await bot.add_cog(AniListSync(bot))
