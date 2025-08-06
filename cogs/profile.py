
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
        """Affiche une carte de membre personnalisée avec les statistiques globales.

        Génère et envoie une carte de profil contenant :
        - Avatar Discord de l'utilisateur
        - Niveau actuel et progression XP
        - Score total aux quiz d'anime
        - Statistiques détaillées des mini-jeux

        En cas d'échec de génération de l'image, un message texte formaté
        est envoyé à la place avec les mêmes informations.

        Args:
            ctx: Le contexte de la commande contenant les informations
                sur l'auteur et le canal
        """
        # Level and XP
        levels = core.load_levels()
        user_data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
        xp = user_data.get("xp", 0)
        level = user_data.get("level", 0)
        next_xp = (level + 1) * 100
        # Quiz score
        scores = core.load_scores()
        quiz_score = scores.get(str(ctx.author.id), 0)
        # Mini-games
        mini_scores = core.get_mini_scores(ctx.author.id)
        # Avatar URL
        avatar_url = None
        try:
            avatar_url = ctx.author.avatar.url
        except Exception:
            avatar_url = None
        try:
            buf = core.generate_profile_card(
                user_name=ctx.author.display_name,
                avatar_url=avatar_url,
                level=level,
                xp=xp,
                next_xp=next_xp,
                quiz_score=quiz_score,
                mini_scores=mini_scores,
            )
            file = discord.File(buf, filename="mycard.jpg")
            embed = discord.Embed(color=discord.Color.dark_orange())
            embed.set_image(url="attachment://mycard.jpg")
            await ctx.send(embed=embed, file=file)
        except Exception:
            # Fallback text representation
            lines = [
                f"🎴 Carte Membre – {ctx.author.display_name}",
                f"Niveau : {level}",
                f"XP : {xp}/{next_xp}",
                f"Score Quiz : {quiz_score}",
            ]
            if mini_scores:
                lines.append("Mini‑jeux :")
                # Human‑readable names for mini‑games
                mapping = {
                    "animequiz": "Quiz",
                    "higherlower": "Higher/Lower",
                    "highermean": "Higher/Mean",
                    "guessyear": "Guess Year",
                    "guessepisodes": "Guess Episodes",
                    "guessgenre": "Guess Genre",
                    "duel": "Duel",
                }
                for g, v in mini_scores.items():
                    # Default to capitalised key if not mapped
                    name = mapping.get(g, g.replace("_", " ").capitalize())
                    lines.append(f"- {name} : {v}")
            await ctx.send("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    """Configure le cog Profile pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Profile(bot))