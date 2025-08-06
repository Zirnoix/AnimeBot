
"""
Module de commandes pour la liaison des comptes AniList et les comparaisons de statistiques.

Ce cog permet aux utilisateurs de :
- Lier leur compte AniList à leur ID Discord
- Délier leur compte à tout moment
- Comparer leurs statistiques avec d'autres utilisateurs

Les liens entre comptes sont persistés via le module core et les statistiques
sont récupérées en temps réel depuis l'API AniList.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from modules import core


class Link(commands.Cog):
    """Cog gérant la liaison des comptes et les comparaisons de statistiques.

    Ce cog fournit trois commandes principales :
    - !linkanilist : Pour lier un compte AniList
    - !unlink : Pour supprimer la liaison
    - !duelstats : Pour comparer ses stats avec un autre utilisateur

    Attributes:
        bot: L'instance du bot Discord
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Initialise le cog Link.

        Args:
            bot: L'instance du bot Discord auquel attacher ce cog
        """
        self.bot = bot

    @commands.command(name="linkanilist")
    async def link_anilist(self, ctx: commands.Context, pseudo: str) -> None:
        """Lie un compte AniList au profil Discord de l'utilisateur.

        Cette commande permet de sauvegarder l'association entre
        l'ID Discord de l'utilisateur et son pseudo AniList. Cette liaison
        est nécessaire pour utiliser les autres commandes du bot.

        Args:
            ctx: Le contexte de la commande
            pseudo: Le nom d'utilisateur AniList à lier
        """
        data = core.load_links()
        data[str(ctx.author.id)] = pseudo
        core.save_links(data)
        await ctx.send(f"✅ Ton compte AniList **{pseudo}** a été lié à ton profil Discord.")

    @commands.command(name="unlink")
    async def unlink(self, ctx: commands.Context) -> None:
        """Supprime la liaison entre le compte Discord et AniList.

        Retire l'association entre l'ID Discord et le pseudo AniList
        précédemment enregistrée. L'utilisateur devra refaire la liaison
        pour utiliser les fonctionnalités nécessitant un compte AniList.

        Args:
            ctx: Le contexte de la commande
        """
        data = core.load_links()
        uid = str(ctx.author.id)
        if uid in data:
            del data[uid]
            core.save_links(data)
            await ctx.send("🔗 Ton lien AniList a bien été supprimé.")
        else:
            await ctx.send("❌ Aucun compte AniList n'était lié à ce profil.")

    @commands.command(name="duelstats")
    async def duelstats(self, ctx: commands.Context, opponent: discord.Member | None = None) -> None:
        """Compare les statistiques AniList entre deux utilisateurs.

        Génère un embed comparant différentes statistiques :
        - Nombre total d'animés vus
        - Score moyen donné
        - Temps total de visionnage en jours
        - Genre favori

        Une flèche indique qui a la plus grande valeur pour chaque stat.

        Args:
            ctx: Le contexte de la commande
            opponent: Le membre Discord avec qui comparer les stats.
                     Si None, affiche un message d'aide.

        Note:
            Les deux utilisateurs doivent avoir lié leur compte AniList
            via la commande !linkanilist au préalable.
        """
        if opponent is None:
            await ctx.send("❌ Utilise : `!duelstats @ami` pour comparer tes stats avec quelqu'un.")
            return
        links = core.load_links()
        uid1, uid2 = str(ctx.author.id), str(opponent.id)
        if uid1 not in links or uid2 not in links:
            await ctx.send("❗ Les deux joueurs doivent avoir lié leur compte avec `!linkanilist`." )
            return
        user1, user2 = links[uid1], links[uid2]
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
        stats: dict[str, dict] = {}
        for u in [user1, user2]:
            res = core.query_anilist(query, {"name": u})
            try:
                a = res["data"]["User"]["statistics"]["anime"]
                fav = sorted(a["genres"], key=lambda g: g["count"], reverse=True)[0]["genre"] if a["genres"] else "N/A"
                stats[u] = {
                    "count": a["count"],
                    "score": round(a["meanScore"], 1) if a["meanScore"] else 0,
                    "days": round(a["minutesWatched"] / 1440, 1) if a["minutesWatched"] else 0,
                    "genre": fav
                }
            except Exception:
                await ctx.send("❌ Impossible de récupérer les statistiques AniList.")
                return
        s1, s2 = stats[user1], stats[user2]
        def who_wins(a, b):
            """Détermine qui a la plus grande valeur entre deux nombres."""
            return "🟰 Égalité" if a == b else ("🔼" if a > b else "🔽")
        embed = discord.Embed(
            title=f"📊 Duel de stats : {ctx.author.display_name} vs {opponent.display_name}",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="🎬 Animés vus",
            value=f"{s1['count']} vs {s2['count']} {who_wins(s1['count'], s2['count'])}",
            inline=False
        )
        embed.add_field(
            name="⭐ Score moyen",
            value=f"{s1['score']} vs {s2['score']} {who_wins(s1['score'], s2['score'])}",
            inline=False
        )
        embed.add_field(
            name="📅 Jours regardés",
            value=f"{s1['days']} vs {s2['days']} {who_wins(s1['days'], s2['days'])}",
            inline=False
        )
        embed.add_field(
            name="🎭 Genre favori",
            value=f"{s1['genre']} vs {s2['genre']}",
            inline=False
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Configure le cog Link pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Link(bot))