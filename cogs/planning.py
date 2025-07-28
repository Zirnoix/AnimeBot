import discord
from discord.ext import commands
import datetime
import requests
import os

class Planning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="planning")
    async def planning(self, ctx):
        username = os.getenv("ANILIST_USERNAME")
        if not username:
            await ctx.send("❌ Aucun nom d’utilisateur Anilist défini dans les variables d’environnement.")
            return

        query = '''
        query ($username: String) {
          MediaListCollection(userName: $username, type: ANIME, status: CURRENT) {
            lists {
              entries {
                media {
                  title {
                    romaji
                  }
                  nextAiringEpisode {
                    airingAt
                    episode
                  }
                }
              }
            }
          }
        }
        '''

        variables = {"username": username}
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables},
            headers={"Content-Type": "application/json"}
        )

        if response.status_code != 200:
            await ctx.send("❌ Erreur lors de la récupération des données Anilist.")
            return

        data = response.json()
        entries = data.get("data", {}).get("MediaListCollection", {}).get("lists", [])
        upcoming_by_day = {i: [] for i in range(7)}  # 0 = lundi, 6 = dimanche

        for group in entries:
            for entry in group.get("entries", []):
                media = entry["media"]
                next_ep = media.get("nextAiringEpisode")
                if next_ep:
                    airing_time = datetime.datetime.fromtimestamp(next_ep["airingAt"], datetime.timezone.utc)
                    weekday = airing_time.weekday()
                    upcoming_by_day[weekday].append({
                        "title": media["title"]["romaji"],
                        "airing_time": airing_time.strftime("%H:%M"),
                        "episode": next_ep["episode"]
                    })

        embed = discord.Embed(title="🗓️ Planning de la semaine (Anilist)", color=0x1abc9c)
        weekdays_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

        for i in range(7):
            shows = upcoming_by_day[i]
            if shows:
                value = "\n".join([
                    f"📺 **{anime['title']}** - Épisode {anime['episode']} à {anime['airing_time']}"
                    for anime in sorted(shows, key=lambda x: x['airing_time'])
                ])
                embed.add_field(name=f"📅 {weekdays_fr[i]}", value=value, inline=False)

        if not any(upcoming_by_day.values()):
            await ctx.send("📭 Aucun épisode à venir trouvé dans ta liste Anilist.")
            return

        embed.set_footer(text="AnimeBot - Planning hebdomadaire")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Planning(bot))
