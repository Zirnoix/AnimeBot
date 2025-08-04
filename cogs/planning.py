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

async def setup(bot):
    await bot.add_cog(Planning(bot))
