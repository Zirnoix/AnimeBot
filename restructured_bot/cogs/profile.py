import io
import discord
from discord.ext import commands

from restructured_bot.modules import core

class Profile(commands.Cog):
    """Cog pour les profils utilisateurs et leurs statistiques (bot)."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="mystats", aliases=["stats"])
    async def my_stats(self, ctx: commands.Context, *, target: str = None) -> None:
        """Affiche la carte de profil (niveau, quiz, mini-jeux) de vous ou d’un autre utilisateur."""
        # Si un nom est fourni, essaie d'afficher le profil de ce membre
        if target:
            # Vérifier si c'est une mention d'utilisateur Discord
            if ctx.message.mentions:
                member = ctx.message.mentions[0]
            else:
                # Rechercher un membre du serveur par nom
                member = discord.utils.find(lambda m: m.name.lower() == target.lower(), ctx.guild.members) if ctx.guild else None
            if member:
                # Afficher la carte de profil du membre Discord
                levels = core.load_levels()
                data = levels.get(str(member.id), {"xp": 0, "level": 0})
                level = data["level"]
                xp = data["xp"]
                next_xp = (level + 1) * 100
                quiz_score = core.load_scores().get(str(member.id), 0)
                mini_scores = core.get_mini_scores(member.id)
                # Générer la carte de profil du bot
                buf = core.generate_profile_card(member.display_name, member.display_avatar.url, level, xp, next_xp, quiz_score, mini_scores)
                file = discord.File(buf, filename="profile.jpg")
                embed = discord.Embed(title=f"🎴 Profil de {member.display_name}", color=discord.Color.blurple())
                embed.set_image(url="attachment://profile.jpg")
                await ctx.send(embed=embed, file=file)
            else:
                # Sinon, tenter d'afficher les stats AniList pour un pseudo donné
                await self.anilist_stats(ctx, target)
        else:
            # Pas de cible : affiche votre propre carte de profil (bot)
            levels = core.load_levels()
            data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
            level = data["level"]
            xp = data["xp"]
            next_xp = (level + 1) * 100
            quiz_score = core.load_scores().get(str(ctx.author.id), 0)
            mini_scores = core.get_mini_scores(ctx.author.id)
            buf = core.generate_profile_card(ctx.author.display_name, ctx.author.display_avatar.url, level, xp, next_xp, quiz_score, mini_scores)
            file = discord.File(buf, filename="profile.jpg")
            embed = discord.Embed(title=f"🎴 Profil de {ctx.author.display_name}", color=discord.Color.blurple())
            embed.set_image(url="attachment://profile.jpg")
            await ctx.send(embed=embed, file=file)

    @commands.command(name="mychart", aliases=["monchart"])
    async def my_chart(self, ctx: commands.Context, username: str = None) -> None:
        """Affiche la répartition des genres préférés (profil AniList lié ou pseudo AniList)."""
        if not username:
            username = core.get_user_anilist(ctx.author.id)
            if not username:
                await ctx.send("❌ Tu dois lier ton compte AniList avec `!linkanilist <pseudo>`.") 
                return
        # Récupérer les statistiques de genres via AniList
        query = '''
        query ($name: String) {
          User(name: $name) {
            statistics {
              anime {
                genres {
                  genre
                  count
                }
              }
            }
          }
        }
        '''
        data = core.query_anilist(query, {"name": username})
        if not data:
            await ctx.send("❌ Impossible de récupérer les données AniList.")
            return
        genres_data = data.get("data", {}).get("User", {}).get("statistics", {}).get("anime", {}).get("genres", [])
        if not genres_data:
            await ctx.send("❌ Aucune donnée de genres trouvée pour cet utilisateur.")
            return
        # Trier les genres par count décroissant et calculer le total
        genres_data.sort(key=lambda g: g["count"], reverse=True)
        total = sum(g["count"] for g in genres_data)
        # Préparer une liste des 5 principaux genres avec pourcentage
        top_genres = genres_data[:5]
        desc_lines = []
        for g in top_genres:
            genre = g["genre"]
            count = g["count"]
            percent = (count / total * 100) if total > 0 else 0
            desc_lines.append(f"• **{genre}** – {count} anime ({percent:.1f}% du total)")
        embed = discord.Embed(
            title=f"📊 Genres favoris de {username}",
            description="\n".join(desc_lines),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    async def anilist_stats(self, ctx: commands.Context, username: str) -> None:
        """Récupère et envoie la carte de stats AniList pour un utilisateur donné."""
        # Requête AniList pour statistiques utilisateur
        query = '''
        query ($name: String) {
          User(name: $name) {
            name
            avatar { large }
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
            await ctx.send("❌ Utilisateur AniList introuvable.")
            return
        user_data = data["data"]["User"]
        anime_stats = user_data["statistics"]["anime"]
        anime_count = anime_stats.get("count", 0) or 0
        mean_score = round(anime_stats.get("meanScore") or 0, 1)
        days_watched = round((anime_stats.get("minutesWatched") or 0) / 1440, 1)
        # Genre favori
        genres = anime_stats.get("genres", [])
        fav_genre = sorted(genres, key=lambda g: g["count"], reverse=True)
        fav_genre = fav_genre[0]["genre"] if fav_genre else "N/A"
        avatar_url = user_data.get("avatar", {}).get("large")
        # Générer la carte de statistiques AniList
        buf = core.generate_stats_card(username, avatar_url, anime_count, days_watched, mean_score, fav_genre)
        file = discord.File(buf, filename="anistats.jpg")
        embed = discord.Embed(title=f"📊 Statistiques AniList – {username}", color=discord.Color.dark_teal())
        embed.set_image(url="attachment://anistats.jpg")
        await ctx.send(embed=embed, file=file)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
