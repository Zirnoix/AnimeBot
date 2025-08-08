
"""
Module de commandes pour l'affichage des cartes de profil et de membre.

Ce cog fournit des commandes permettant d'afficher une carte de profil personnalisée
qui résume les statistiques globales d'un utilisateur, notamment :
- Niveau et progression XP
- Score dans les quiz d'anime
- Participation aux différents mini-jeux
- Avatar Discord et nom d'utilisateur

Les données sont récupérées via le module core et présentées sous forme
d'une carte visuelle ou d'un embed Discord en cas d'erreur.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from modules import core


class Profile(commands.Cog):
    """Cog gérant l'affichage des cartes de profil et informations utilisateur.

    Ce cog propose principalement la commande !mycard qui génère une carte
    de membre personnalisée regroupant toutes les statistiques de l'utilisateur
    dans le bot.

    Attributes:
        bot: L'instance du bot Discord auquel ce cog est attaché
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Initialise le cog Profile.

        Args:
            bot: L'instance du bot Discord
        """
        self.bot = bot

        @commands.command(name="mycard")
        async def mycard(self, ctx: commands.Context) -> None:
            """Affiche une carte de membre propre avec les statistiques globales."""
            levels = core.load_levels()
            user_data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
            xp = user_data.get("xp", 0)
            level = user_data.get("level", 0)
            next_xp = (level + 1) * 100

            scores = core.load_scores()
            quiz_score = scores.get(str(ctx.author.id), 0)
            mini_scores = core.get_mini_scores(ctx.author.id)

            embed = discord.Embed(
                title=f"🎴 Carte de {ctx.author.display_name}",
                description=(
                    f"**Niveau :** {level}\n"
                    f"**XP :** {xp}/{next_xp}\n"
                    f"**🏆 Score Quiz :** {quiz_score}"
                ),
                color=discord.Color.orange(),
            )
    
            if mini_scores:
                mapping = {
                    "animequiz": "Quiz",
                    "higherlower": "Higher/Lower",
                    "highermean": "Higher/Mean",
                    "guessyear": "Guess Year",
                    "guessepisodes": "Guess Episodes",
                    "guessgenre": "Guess Genre",
                    "duel": "Duel",
                }
                value = ""
                for g, v in mini_scores.items():
                    name = mapping.get(g, g.replace("_", " ").capitalize())
                    value += f"• **{name}** : {v}\n"
                embed.add_field(name="🎮 Mini‑jeux", value=value, inline=False)

            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Configure le cog Profile pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Profile(bot))
