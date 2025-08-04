import discord
from discord.ext import commands
from modules import anilist

class Planning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="planning")
    async def planning(self, ctx):
        embed = discord.Embed(
            title="📆 Planning des Animes de la Semaine",
            description="Voici les sorties prévues cette semaine :",
            color=discord.Color.teal()
        )

        try:
            schedule = anilist.get_weekly_schedule()
        except Exception:
            await ctx.send("❌ Impossible de récupérer le planning.")
            return

        for day, animes in schedule.items():
            value = ""
            for anime in animes:
                time = anime.get("time", "?")
                title = anime["title"]
                url = anime["url"]
                value += f"🕒 `{time}` — [{title}]({url})\n"
            if value:
                embed.add_field(name=f"📅 {day}", value=value, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="next")
    async def next_episode(self, ctx):
        """⏭️ Affiche le prochain épisode à venir sous forme d’image"""
        data = await get_next_airing_anime_data()
        if not data:
            await ctx.send("❌ Impossible de récupérer les infos du prochain épisode.")
            return

        image_bytes = await asyncio.to_thread(
            generate_next_anime_image,
            data["title"],
            data["episode"],
            data["airing_time"],
            data["cover_url"]
        )
    
        file = discord.File(image_bytes, filename="next.png")
        embed = discord.Embed(
            title=f"🎬 Prochain épisode à venir : {data['title']}",
            color=0xe67e22
        )
        embed.set_image(url="attachment://next.png")
        await ctx.send(embed=embed, file=file)

async def setup(bot):
    await bot.add_cog(Planning(bot))
