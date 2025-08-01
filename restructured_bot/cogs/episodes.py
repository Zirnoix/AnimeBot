"""
Commands related to airing schedules and upcoming episodes.

This cog provides commands to display upcoming episodes for the bot owner's
AniList account as well as per-user schedules. It relies on helper
functions from ``modules.core`` to query AniList and format results.
"""

from __future__ import annotations

import discord
from discord.ext import commands
from datetime import datetime

from ..modules import core


class Episodes(commands.Cog):
    """Cog for episode planning and notifications."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="prochains")
    async def prochains(self, ctx: commands.Context, *args: str) -> None:
        """Affiche les prochains épisodes à venir pour le compte AniList configuré.

        Utilisation : ``!prochains [genre] [nombre|all]``. Vous pouvez
        spécifier un genre pour filtrer et un nombre maximum d'entrées (ou
        ``all`` pour tout afficher, limité à 100).
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
        """Affiche le prochain épisode à venir dans la liste du bot (compte global)."""
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
        """Affiche le prochain épisode à venir pour l'utilisateur ayant lié son compte AniList."""
        username = core.get_user_anilist(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu n’as pas encore lié ton compte AniList. Utilise `!linkanilist <pseudo>`.")
            return
        episodes = core.get_upcoming_episodes(username)
        if not episodes:
            await ctx.send("📭 Aucun épisode à venir dans ta liste.")
            return
        next_ep = min(episodes, key=lambda e: e["airingAt"])
        dt = datetime.fromtimestamp(next_ep["airingAt"], tz=core.TIMEZONE)
        # Generate personalised image card
        try:
            buf = core.generate_next_image(next_ep, dt, tagline="Ton prochain épisode")
            file = discord.File(buf, filename="mynext.jpg")
            embed = discord.Embed(title="🎬 Ton prochain épisode", color=discord.Color.purple())
            embed.set_image(url="attachment://mynext.jpg")
            await ctx.send(embed=embed, file=file)
        except Exception:
            # Fallback to text embed if image generation fails
            embed = discord.Embed(
                title="🎬 Ton prochain épisode à venir",
                description=f"{next_ep['title']} — Épisode {next_ep['episode']}",
                color=discord.Color.purple(),
            )
            embed.add_field(name="Date", value=dt.strftime("%d/%m/%Y à %H:%M"), inline=False)
            await ctx.send(embed=embed)

    @commands.command(name="planning")
    async def planning(self, ctx: commands.Context) -> None:
        """Affiche le planning hebdomadaire global des épisodes."""
        episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
        if not episodes:
            await ctx.send("Aucun planning disponible.")
            return
        # Group by weekday in French
        planning: dict[str, list[str]] = {day: [] for day in core.JOURS_FR.values()}
        for ep in episodes:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            jour = core.JOURS_FR[dt.strftime("%A")]
            time_str = dt.strftime("%H:%M")
            planning[jour].append(f"• {ep['title']} — Ép. {ep['episode']} ({time_str})")
        # Send an embed per day that has entries
        for day, items in planning.items():
            if not items:
                continue
            embed = discord.Embed(
                title=f"📅 Planning du {day}",
                description="\n".join(items[:10]),
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)

    @commands.command(name="monplanning")
    async def mon_planning(self, ctx: commands.Context) -> None:
        """Affiche les prochains épisodes pour l'utilisateur ayant lié son AniList."""
        username = core.get_user_anilist(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu n’as pas encore lié ton compte AniList. Utilise `!linkanilist <pseudo>`.")
            return
        episodes = core.get_upcoming_episodes(username)
        if not episodes:
            await ctx.send(f"📭 Aucun épisode à venir trouvé pour **{username}**.")
            return
        embed = discord.Embed(
            title=f"📅 Planning personnel – {username}",
            description="Voici les prochains épisodes à venir dans ta liste.",
            color=discord.Color.teal(),
        )
        for ep in sorted(episodes, key=lambda e: e["airingAt"])[:10]:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            emoji = core.genre_emoji(ep.get("genres", []))
            date_fr = core.format_date_fr(dt, "EEEE d MMMM")
            heure = dt.strftime('%H:%M')
            embed.add_field(name=f"{emoji} {ep['title']} – Épisode {ep['episode']}", value=f"🕒 {date_fr} à {heure}", inline=False)
        # Set thumbnail to first entry's image
        if episodes:
            embed.set_thumbnail(url=episodes[0].get("image"))
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Episodes(bot))
