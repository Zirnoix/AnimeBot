        
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
        """Affiche une carte de membre stylée avec les statistiques globales."""
        user_id = str(ctx.author.id)

        # Chargement données
        levels = core.load_levels()
        user_data = levels.get(user_id, {"xp": 0, "level": 0})
        xp = user_data.get("xp", 0)
        level = user_data.get("level", 0)
        next_xp = xp_for_next_level(level)

        # Progression (max 20 segments)
        total_segments = 20
        progress = max(0, min(total_segments, int((xp / next_xp) * total_segments)))

        # Couleurs par palier
        level_colors = [
            (150, "🌈"),  # arc-en-ciel
            (140, "⬜"),
            (130, "🟫"),
            (120, "🟪"),
            (110, "🟦"),
            (100, "🟩"),
            (90, "🟥"),
            (80, "🟧"),
            (70, "🟨"),
            (60, "⬜"),
            (50, "🟫"),
            (40, "🟪"),
            (30, "🟦"),
            (20, "🟥"),
            (10, "🟦"),
            (0, "🟩"),
        ]

        color_emoji = next(c for lvl, c in level_colors if level >= lvl)

        # Construction de la barre
        if color_emoji == "🌈":
            filled = "🌈" * progress
        else:
            filled = color_emoji * progress
        empty = "⬛" * (total_segments - progress)
        bar = filled + empty

        # Titre actuel
        title = core.get_title_for_level(level)

        # Vérifie si le titre a changé
        titles_data = core.load_titles()
        previous_title = titles_data.get(user_id)

        if previous_title != title:
            titles_data[user_id] = title
            core.save_titles(titles_data)

            if previous_title is not None and level > 0:
                await ctx.send(f"🎉 **{ctx.author.display_name}** vient de passer au rang {title} !")

        # Score quiz et mini-jeux
        scores = core.load_scores()
        quiz_score = scores.get(user_id, 0)
        mini_scores = core.get_mini_scores(int(user_id))

        # Embed final
        embed = discord.Embed(
            title=f"🎴 Profil de {ctx.author.display_name}",
            color=discord.Color.from_rgb(255 - min(level * 2, 200), 100 + min(level, 100), 30)
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="🎖️ Titre", value=title, inline=True)
        embed.add_field(name="🧬 Niveau", value=f"{level}", inline=True)
        embed.add_field(name="🧪 XP", value=f"{xp} / {next_xp}", inline=True)
        embed.add_field(name="📈 Progression", value=bar, inline=False)
        embed.add_field(name="🏆 Score Quiz", value=f"{quiz_score}", inline=False)

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
            embed.add_field(name="🎮 Mini-jeux", value=value, inline=False)

        await ctx.send(embed=embed)



async def setup(bot: commands.Bot) -> None:
    """Configure le cog Profile pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Profile(bot))
