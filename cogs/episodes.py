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
from modules.image import generate_next_card


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
    async def next_cmd(self, ctx):
        try:
            item = core.get_my_next_airing_one()  # <-- TON AniList via variable env
        except Exception as e:
            await ctx.send(f"⚠️ Impossible de récupérer le prochain épisode.\n`{type(e).__name__}: {e}`")
            return

        if not item:
            await ctx.send("⚠️ Aucun épisode à venir trouvé.")
            return

        item["when"] = core.format_airing_datetime_fr(item.get("airingAt"), "Europe/Paris")

        img_path = generate_next_card(item, out_path="/tmp/next_card.png")

        embed = discord.Embed(title="⏭️ Prochain épisode", color=0x00B0F4)
        embed.set_image(url="attachment://next_card.png")
        embed.set_footer(text=f"Demandé par {ctx.author.display_name}")

        file = discord.File(img_path, filename="next_card.png")
        await ctx.send(embed=embed, file=file)
        
    @commands.command(name="monnext")
    async def monnext_cmd(self, ctx):
        # Récupère les séries suivies par l’utilisateur + prochain épisode
        items = core.get_user_next_airing(ctx.author.id, limit=8)  # adapte au nom réel
        if not items:
            await ctx.send(f"{EMOJI['warn']} Rien à venir pour toi pour l’instant.")
            return

        title = f"{EMOJI['next']} Tes prochains épisodes"
        e = make_embed(title=title, color=THEME["success"], footer=f"{ctx.author.display_name}")
        if ctx.author.display_avatar:
            e.set_thumbnail(url=ctx.author.display_avatar.url)

        lines = []
        for it in items:
            t = safe(it.get("title_romaji") or it.get("title_english") or it.get("title_native"))
            ep = it.get("episode") or 1
            when_txt = core.humanize_airing_time(it)
            lines.append(fmt_anime_line(t, ep, when_txt))

        add_fields(e, [(f"{EMOJI['tv']} À venir pour toi", "\n\n".join(lines))], inline=False)
        await ctx.send(embed=e)

    @commands.command(name="planning")
    async def planning(self, ctx: commands.Context) -> None:
        """Affiche le planning hebdomadaire global des épisodes.

        Organise les épisodes par jour de la semaine dans des embeds distincts.
        Utilise la liste globale configurée.

        Args:
            ctx: Le contexte de la commande
        """
        episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)

        if not episodes:
            await ctx.send("📭 Aucun épisode prévu cette semaine.")
            return

        # Organiser les épisodes par jour
        planning: dict[str, list] = {}
        for ep in episodes:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            jour = core.JOURS_FR[dt.strftime("%A")]
            if jour not in planning:
                planning[jour] = []
            planning[jour].append((ep, dt))

        # Créer un embed par jour
        for jour, episodes_jour in planning.items():
            # Trier par heure et limiter à 10 épisodes
            episodes_jour.sort(key=lambda x: x[1])
            episodes_jour = episodes_jour[:10]

            embed = discord.Embed(
                title=f"📅 Planning {jour}",
                color=discord.Color.blurple(),
            )

            for ep, dt in episodes_jour:
                heure = dt.strftime("%H:%M")
                emoji = core.genre_emoji(ep.get("genres", []))
                embed.add_field(
                    name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                    value=f"⏰ {heure}",
                    inline=False
                )

            await ctx.send(embed=embed)

    @commands.command(name="monplanning")
    async def mon_planning(self, ctx: commands.Context) -> None:
        """Affiche le planning hebdomadaire personnel de l'utilisateur.

        Nécessite d'avoir lié son compte AniList.
        Organise les épisodes par jour depuis la liste personnelle.

        Args:
            ctx: Le contexte de la commande
        """
        # Vérifier si l'utilisateur a lié son compte
        links = core.load_links()
        user_id = str(ctx.author.id)

        if user_id not in links:
            await ctx.send("❌ Tu dois d'abord lier ton compte AniList avec `!linkanilist <pseudo>`")
            return

        # Récupérer les épisodes de l'utilisateur
        episodes = core.get_upcoming_episodes(links[user_id])

        if not episodes:
            await ctx.send("📭 Aucun épisode prévu cette semaine dans ta liste.")
            return

        # Organiser les épisodes par jour
        planning: dict[str, list] = {}
        for ep in episodes:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            jour = core.JOURS_FR[dt.strftime("%A")]
            if jour not in planning:
                planning[jour] = []
            planning[jour].append((ep, dt))

        # Créer un embed par jour
        for jour, episodes_jour in planning.items():
            # Trier par heure et limiter à 10 épisodes
            episodes_jour.sort(key=lambda x: x[1])
            episodes_jour = episodes_jour[:10]

            embed = discord.Embed(
                title=f"📅 Ton planning {jour}",
                color=discord.Color.blurple(),
            )

            for ep, dt in episodes_jour:
                heure = dt.strftime("%H:%M")
                emoji = core.genre_emoji(ep.get("genres", []))
                embed.add_field(
                    name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                    value=f"⏰ {heure}",
                    inline=False
                )

            await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Configure le cog Episodes pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Episodes(bot))
