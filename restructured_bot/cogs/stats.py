"""
Commands to display profile statistics and genre charts.

This cog fetches user statistics from AniList and presents them in a
readable embed. It also offers a simple bar chart in text form for
visualising favourite genres.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from ..modules import core


class Stats(commands.Cog):
    """Cog for profile stats and charts."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="mystats")
    async def mystats(self, ctx: commands.Context) -> None:
        """Affiche tes statistiques AniList avec un design personnalisé."""
        username = core.get_user_anilist(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu dois lier ton compte avec `!linkanilist <pseudo>` avant d’utiliser cette commande.")
            return
        # Fetch stats from AniList
        query = '''
        query ($name: String) {
          User(name: $name) {
            statistics {
              anime {
                count
                minutesWatched
                meanScore
                genres { genre count }
              }
            }
          }
        }
        '''
        data = core.query_anilist(query, {"name": username})
        if not data or not data.get("data", {}).get("User"):
            await ctx.send(f"❌ Impossible de récupérer les données AniList pour **{username}**.")
            return
        stats = data["data"]["User"]["statistics"]["anime"]
        genres = stats.get("genres", [])
        fav_genre = sorted(genres, key=lambda g: g["count"], reverse=True)[0]["genre"] if genres else "N/A"
        days = stats.get("minutesWatched", 0) / 1440
        count = stats.get("count", 0)
        mean = stats.get("meanScore", 0)
        # Generate image card
        avatar_url = None
        try:
            avatar_url = ctx.author.avatar.url
        except Exception:
            avatar_url = None
        try:
            buf = core.generate_stats_card(
                user_name=ctx.author.display_name,
                avatar_url=avatar_url,
                anime_count=count,
                days_watched=days,
                mean_score=mean,
                fav_genre=fav_genre,
            )
            file = discord.File(buf, filename="mystats.jpg")
            embed = discord.Embed(color=discord.Color.dark_teal())
            embed.set_image(url="attachment://mystats.jpg")
            await ctx.send(embed=embed, file=file)
        except Exception:
            # Fallback to simple embed
            embed = discord.Embed(
                title=f"📊 Statistiques AniList – {ctx.author.display_name}",
                color=discord.Color.blue(),
            )
            embed.add_field(name="🎬 Animés vus", value=str(count), inline=False)
            embed.add_field(name="🕒 Temps total", value=f"{days:.1f} jours", inline=False)
            embed.add_field(name="⭐ Score moyen", value=str(round(mean, 1)), inline=False)
            embed.add_field(name="🎭 Genre préféré", value=fav_genre, inline=False)
            await ctx.send(embed=embed)

    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context, username: str) -> None:
        """Affiche les statistiques d’un utilisateur AniList spécifié."""
        await self._send_stats(ctx, username, username)

    async def _send_stats(self, ctx: commands.Context, username: str, display_name: str) -> None:
        query = '''
        query ($name: String) {
          User(name: $name) {
            name
            statistics {
              anime {
                count
                minutesWatched
                meanScore
                genres { genre count }
              }
            }
          }
        }
        '''
        data = core.query_anilist(query, {"name": username})
        if not data or not data.get("data", {}).get("User"):
            await ctx.send(f"❌ Impossible de récupérer le profil **{username}**.")
            return
        user = data["data"]["User"]
        stats = user["statistics"]["anime"]
        genres = stats.get("genres", [])
        fav_genre = sorted(genres, key=lambda g: g["count"], reverse=True)[0]["genre"] if genres else "N/A"
        days = round(stats.get("minutesWatched", 0) / 1440, 1)
        embed = discord.Embed(
            title=f"📊 Statistiques AniList – {display_name}",
            color=discord.Color.blue(),
        )
        embed.add_field(name="🎬 Animés vus", value=str(stats.get("count", 0)), inline=False)
        embed.add_field(name="🕒 Temps total", value=f"{days} jours", inline=False)
        embed.add_field(name="⭐ Score moyen", value=str(round(stats.get("meanScore", 0), 1)), inline=False)
        embed.add_field(name="🎭 Genre préféré", value=fav_genre, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="monchart")
    async def monchart(self, ctx: commands.Context, username: str | None = None) -> None:
        """Affiche un histogramme textuel des genres les plus regardés.

        Si aucun nom n'est fourni, l'utilisateur doit avoir lié son AniList.
        """
        links = core.load_links()
        if not username:
            username = links.get(str(ctx.author.id))
            if not username:
                await ctx.send("❌ Tu dois lier ton compte AniList avec `!linkanilist <pseudo>`.")
                return
        query = '''
        query ($name: String) {
          User(name: $name) {
            statistics {
              anime {
                genres { genre count }
              }
            }
          }
        }
        '''
        data = core.query_anilist(query, {"name": username})
        if not data or not data.get("data", {}).get("User"):
            await ctx.send("❌ Impossible de récupérer les données AniList.")
            return
        genre_stats = data["data"]["User"]["statistics"]["anime"]["genres"]
        # Compute top genres and percentages
        top_genres = sorted(genre_stats, key=lambda g: g["count"], reverse=True)[:6]
        total = sum(g["count"] for g in top_genres) or 1
        chart_data: list[tuple[str, int, int]] = []
        for g in top_genres:
            percent = int((g["count"] / total) * 100)
            chart_data.append((g["genre"], g["count"], percent))
        # Always display a text-based chart for readability
        lines = [f"📊 Genres les plus regardés de **{username}** :\n"]
        def emoji_genre(name: str) -> str:
            emojis = {
                "Action": "⚔️", "Fantasy": "🧙", "Romance": "💖", "Comedy": "😂",
                "Drama": "🎭", "Horror": "👻", "Sci-Fi": "🚀", "Music": "🎵",
                "Sports": "⚽", "Slice of Life": "🍃", "Psychological": "🧠",
                "Adventure": "🌍", "Mecha": "🤖", "Supernatural": "🔮",
                "Ecchi": "😳", "Mystery": "🕵️"
            }
            return emojis.get(name, "📺")
        def bar(percent: int) -> str:
            filled = int(percent / 10)
            return "▰" * filled + "▱" * (10 - filled)
        for genre, count, percent in chart_data:
            lines.append(f"{emoji_genre(genre)} {genre:<13} {bar(percent)}  {percent}%")
        # Use an embed for a cleaner look
        embed = discord.Embed(
            title=f"Genres préférés de {username}",
            description="\n".join(lines),
            color=discord.Color.dark_green(),
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))