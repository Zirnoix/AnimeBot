
"""
Module de commandes pour afficher les statistiques de profil et les graphiques de genres.

Ce cog récupère les statistiques des utilisateurs depuis AniList et les présente sous forme
d'embeds Discord. Il propose également :
- Une carte de statistiques personnalisée avec avatar pour la commande mystats
- Un graphique en barres textuel pour visualiser les genres préférés
- Des statistiques détaillées comme le temps de visionnage et les scores moyens

Classes:
    Stats: Cog gérant les commandes de statistiques et graphiques
"""

from __future__ import annotations

import discord
from discord.ext import commands

from modules import core

# --- EMOJI & couleurs locales (fallback) ---
EMOJI = {"stats": "📊", "ok": "✅", "warn": "⚠️", "tv": "📺"}
COLOR_PRIMARY = 0x5865F2

def text_bar(current: int, total: int, width: int = 16) -> str:
    total = max(1, int(total or 1))
    current = max(0, int(current or 0))
    filled = int(round(width * current / total))
    return f"[{'█' * filled}{'—' * (width - filled)}] {current}/{total}"


class Stats(commands.Cog):
    """Cog pour gérer l'affichage des statistiques et graphiques de profil.

    Ce cog fournit des commandes pour :
    - Voir ses propres stats avec une carte personnalisée (!mystats)
    - Voir les stats d'un autre utilisateur (!stats <pseudo>)
    - Visualiser ses genres préférés (!monchart [pseudo])

    Attributes:
        bot: L'instance du bot Discord
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Initialise le cog Stats.

        Args:
            bot: L'instance du bot Discord auquel attacher ce cog
        """
        self.bot = bot

    @commands.command(name="mystats")
    async def mystats_cmd(self, ctx):
        try:
            s = core.get_anilist_stats_for_discord(ctx.author.id, fallback_env=True)
        except Exception as e:
            await ctx.send(f"{EMOJI['warn']} Impossible de récupérer tes stats AniList.\n`{type(e).__name__}: {e}`")
            return

        if not s:
            await ctx.send(f"{EMOJI['warn']} Aucun compte AniList lié. Utilise `!linkanilist <pseudo>`.")
            return

        count = s.get("count", 0)
        minutes = s.get("minutesWatched", 0)
        mean = s.get("meanScore", 0)
        genre = s.get("favoriteGenre", "—")

        e = discord.Embed(
            title=f"{EMOJI['stats']} Tes stats AniList",
            color=COLOR_PRIMARY,
            description=(
                f"**Animés vus :** {count}\n"
                f"**Temps total :** {core.humanize_minutes(minutes)}\n"
                f"**Score moyen :** {mean:.1f}\n"
                f"**Genre favori :** {genre}"
            )
        )
        if ctx.author.display_avatar:
            e.set_thumbnail(url=ctx.author.display_avatar.url)
        e.set_footer(text=f"Demandé par {ctx.author.display_name}")

        await ctx.send(embed=e)

    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context, username: str) -> None:
        """Affiche les statistiques d'un utilisateur AniList spécifié.

        Récupère et affiche les statistiques basiques d'un profil AniList :
        - Nombre d'animés vus
        - Temps total de visionnage
        - Score moyen
        - Genre favori

        Args:
            ctx: Le contexte de la commande
            username: Le nom d'utilisateur AniList dont afficher les stats
        """
        await self._send_stats(ctx, username, username)

    async def _send_stats(self, ctx: commands.Context, username: str, display_name: str) -> None:
        """Fonction utilitaire pour récupérer et envoyer les stats d'un utilisateur.

        Effectue la requête GraphQL vers l'API AniList et formate les données
        dans un embed Discord.

        Args:
            ctx: Le contexte de la commande
            username: Le nom d'utilisateur AniList
            display_name: Le nom à afficher dans l'embed (peut différer du username)
        """
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
        """Affiche un histogramme des genres les plus regardés.

        Génère un graphique en barres textuel montrant :
        - Les 6 genres les plus regardés
        - Le pourcentage relatif de chaque genre
        - Une barre de progression avec des caractères spéciaux
        - Une icône adaptée à chaque genre

        Args:
            ctx: Le contexte de la commande
            username: Le nom d'utilisateur AniList (optionnel)
                     Si non fourni, utilise le compte lié de l'utilisateur
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
    """Ajoute le cog Stats au bot.

    Args:
        bot: L'instance du bot auquel ajouter le cog
    """
    await bot.add_cog(Stats(bot))
