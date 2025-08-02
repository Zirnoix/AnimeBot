import discord
from discord.ext import commands

from restructured_bot.modules import core

class Stats(commands.Cog):
    """Cog pour les commandes de comparaison et de classement AniList."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="duelstats")
    async def duel_stats(self, ctx: commands.Context, opponent: discord.Member = None) -> None:
        """Compare les statistiques AniList entre vous et un ami mentionné."""
        if opponent is None:
            await ctx.send("❌ Utilise : `!duelstats @ami` pour comparer vos stats AniList.")
            return
        embed = core.get_duel_stats(ctx.author.id, opponent.id)
        if embed is None:
            await ctx.send("❗ Les deux utilisateurs doivent avoir lié leur compte AniList avec `!linkanilist`.")
        else:
            await ctx.send(embed=embed)

    @commands.command(name="classementgenre")
    async def classement_genre(self, ctx: commands.Context, *, genre: str = None) -> None:
        """Affiche le classement des membres liés ayant vu le plus d'animés d'un genre donné."""
        if not genre:
            await ctx.send("❌ Utilise : `!classementgenre <Genre>` (exemple : `!classementgenre action`).")
            return
        genre = genre.capitalize()
        links = core.load_links()
        if not links:
            await ctx.send("❌ Aucun compte AniList n'est lié pour effectuer le classement.")
            return
        rankings = []
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
        # Récupérer le count de chaque utilisateur pour le genre donné
        for uid, anilist_name in links.items():
            data = core.query_anilist(query, {"name": anilist_name})
            if not data:
                continue
            try:
                genres = data["data"]["User"]["statistics"]["anime"]["genres"]
            except Exception:
                continue
            count = 0
            for g in genres:
                if g["genre"] == genre:
                    count = g["count"]
                    break
            rankings.append((uid, count))
        # Filtrer ceux qui ont au moins 1 anime de ce genre et trier
        rankings = [r for r in rankings if r[1] > 0]
        if not rankings:
            await ctx.send(f"❌ Aucun utilisateur n'a regardé d'anime de genre **{genre}**.")
            return
        rankings.sort(key=lambda x: x[1], reverse=True)
        top = rankings[:5]
        desc = ""
        for rank, (uid, count) in enumerate(top, start=1):
            try:
                user = await self.bot.fetch_user(int(uid))
                desc += f"{rank}. **{user.display_name}** — {count} animés\n"
            except Exception:
                continue
        embed = discord.Embed(
            title=f"🏅 Classement – Passionnés de {genre}",
            description=desc,
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    @commands.command(name="topanime")
    async def top_anime(self, ctx: commands.Context) -> None:
        """Affiche le Top 10 des animés les mieux notés sur AniList."""
        query = '''
        query {
          Page(perPage: 10) {
            media(type: ANIME, sort: SCORE_DESC, isAdult: false) {
              title { romaji }
              averageScore
              siteUrl
            }
          }
        }
        '''
        data = core.query_anilist(query)
        if not data or "data" not in data or not data["data"].get("Page"):
            await ctx.send("❌ Impossible de récupérer le top des animés.")
            return
        entries = data["data"]["Page"]["media"]
        desc = ""
        for i, anime in enumerate(entries, start=1):
            name = anime.get("title", {}).get("romaji", "Inconnu")
            score = anime.get("averageScore", "??")
            url = anime.get("siteUrl", "")
            desc += f"{i}. [{name}]({url}) – ⭐ {score}\n"
        embed = discord.Embed(title="🔥 Top 10 animés (meilleures notes)", description=desc, color=discord.Color.gold())
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
