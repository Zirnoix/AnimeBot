"""
Module de commandes pour la gestion des plannings et épisodes à venir.

Ce cog est le cœur du bot, permettant aux utilisateurs de :
- Voir les prochains épisodes des animes qu'ils suivent
- Consulter leur planning personnel ou global
- Filtrer les sorties par genre
- Obtenir des notifications visuelles pour les prochains épisodes

Les données sont récupérées en temps réel depuis AniList via le module core
et sont présentées sous forme de cartes personnalisées ou d'embeds Discord.
"""

from __future__ import annotations

import discord
from discord.ext import commands
from datetime import datetime

from modules import core


class Episodes(commands.Cog):
    """Cog gérant les plannings et les notifications d'épisodes.

    Ce cog propose plusieurs commandes pour suivre les sorties d'épisodes :
    - !prochains : Liste des prochains épisodes avec filtres
    - !next/monnext : Prochain épisode (global ou personnel)
    - !planning/monplanning : Planning hebdomadaire (global ou personnel)

    Attributes:
        bot: L'instance du bot Discord
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Initialise le cog Episodes.

        Args:
            bot: L'instance du bot Discord auquel attacher ce cog
        """
        self.bot = bot

    @commands.command(name="prochains")
    async def prochains(self, ctx: commands.Context, *args: str) -> None:
        """Affiche la liste des prochains épisodes à venir.

        Permet de voir les prochaines sorties avec options de filtrage :
        - Par genre (ex: "Action", "Romance", etc.)
        - Par nombre d'épisodes à afficher

        Args:
            ctx: Le contexte de la commande
            *args: Arguments optionnels :
                - Un genre pour filtrer les résultats
                - Un nombre ou "all" pour la limite d'affichage

        Examples:
            !prochains           -> 10 prochains épisodes
            !prochains 20        -> 20 prochains épisodes
            !prochains Romance   -> Prochains épisodes de romance
            !prochains Romance 5 -> 5 prochains épisodes de romance
        """
        filter_genre: str | None = None
        limit: int = 10
        for arg in args:
            if arg.isdigit():
                limit = min(100, int(arg))
            elif arg.lower() in {"all", "tout"}:
                limit = 100
            else:
                filter_genre = arg.capitalize()
        episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
        if not episodes:
            await ctx.send("Aucun épisode à venir.")
            return
        if filter_genre:
            episodes = [ep for ep in episodes if filter_genre in ep.get("genres", [])]
            if not episodes:
                await ctx.send(f"Aucun épisode trouvé pour le genre **{filter_genre}**.")
                return
        episodes = sorted(episodes, key=lambda e: e["airingAt"])[:limit]
        embed = discord.Embed(
            title="📅 Prochains épisodes",
            description=f"Épisodes à venir{f' pour le genre **{filter_genre}**' if filter_genre else ''} :",
            color=discord.Color.blurple(),
        )
        for ep in episodes:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            date_fr = core.format_date_fr(dt, "d MMMM")
            jour = core.JOURS_FR[dt.strftime("%A")]
            heure = dt.strftime("%H:%M")
            value = f"🗓️ {jour} {date_fr} à {heure}"
            emoji = core.genre_emoji(ep.get("genres", []))
            embed.add_field(name=f"{emoji} {ep['title']} — Épisode {ep['episode']}", value=value, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="next")
    async def next_episode(self, ctx: commands.Context) -> None:
        """Affiche le prochain épisode à venir dans la liste globale.

        Génère une carte visuelle avec :
        - Le titre de l'anime
        - Le numéro d'épisode
        - La date et heure de sortie
        - Une image de l'anime

        En cas d'erreur, retombe sur un embed textuel simple.

        Args:
            ctx: Le contexte de la commande
        """
        episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
        if not episodes:
            await ctx.send("📭 Aucun épisode à venir trouvé dans la liste configurée.")
            return
        next_ep = min(episodes, key=lambda e: e["airingAt"])
        dt = datetime.fromtimestamp(next_ep["airingAt"], tz=core.TIMEZONE)
        # Generate image card
        try:
            buf = core.generate_next_image(next_ep, dt, tagline="Prochain épisode")
            file = discord.File(buf, filename="next.jpg")
            embed = discord.Embed(title="🎬 Prochain épisode", color=discord.Color.blurple())
            embed.set_image(url="attachment://next.jpg")
            await ctx.send(embed=embed, file=file)
        except Exception:
            # Fallback to text embed if image generation fails
            embed = discord.Embed(
                title="🎬 Prochain épisode",
                description=f"{next_ep['title']} — Épisode {next_ep['episode']}",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Date", value=dt.strftime("%d/%m/%Y à %H:%M"), inline=False)
            await ctx.send(embed=embed)

    @commands.command(name="monnext")
    async def my_next(self, ctx: commands.Context) -> None:
        """Affiche le prochain épisode pour l'utilisateur.

        Similaire à !next mais utilise la liste personnelle de l'utilisateur.
        Nécessite d'avoir lié son compte AniList au préalable.

        Génère une carte personnalisée avec :
        - Le titre de l'anime
        - Le numéro d'épisode
        - La date et heure de sortie
        - Une image de l'anime

        Args:
            ctx: Le contexte de la commande
        """
        # Code existant...

    @commands.command(name="planning")
    async def planning(self, ctx: commands.Context) -> None:
        """Affiche le planning hebdomadaire global des épisodes.

        Organise les épisodes par jour de la semaine et envoie un embed
        distinct pour chaque jour contenant des sorties.

        Format :
        - Un embed par jour
        - Liste des épisodes avec leur heure de sortie
        - Limité aux 10 premiers épisodes par jour

        Args:
            ctx: Le contexte de la commande
        """
        # Code existant...

    @commands.command(name="monplanning")
    async def mon_planning(self, ctx: commands.Context) -> None:
        """Affiche le planning personnel de l'utilisateur.

        Nécessite d'avoir lié son compte AniList au préalable.
        Affiche les 10 prochains épisodes à venir dans un embed avec :
        - Titre de l'anime avec emoji de genre
        - Numéro d'épisode
        - Date et heure de sortie en français
        - Miniature du premier anime de la liste

        Args:
            ctx: Le contexte de la commande
        """
        # Code existant...


async def setup(bot: commands.Bot) -> None:
    """Configure le cog Episodes pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Episodes(bot))