"""
Anime tracker commands.

This cog allows users to subscribe to specific anime titles and receive
notifications when new episodes air. Users can add or remove titles
from their personal watchlist and list their current subscriptions.
"""

from __future__ import annotations

import logging
import asyncio
from typing import Optional, List, Dict

import discord
from discord.ext import commands

from modules import core

logger = logging.getLogger(__name__)

class Tracker(commands.Cog):
    """Gestion du suivi d'animes et des notifications."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def find_anime_matches(self, search: str) -> List[Dict]:
        """Recherche les animes correspondant à la recherche."""
        query = '''
        query ($search: String) {
          Page(perPage: 5) {
            media(type: ANIME, search: $search) {
              id
              title {
                romaji
                english
                native
              }
              status
              nextAiringEpisode {
                episode
              }
              format
              episodes
              season
              seasonYear
            }
          }
        }
        '''
        try:
            result = core.query_anilist(query, {"search": search})
            if result and "data" in result:
                return result["data"]["Page"]["media"]
            return []
        except Exception as e:
            logger.error(f"Erreur recherche anime: {e}")
            return []

    @commands.group(name="track", invoke_without_command=True)
    async def track(self, ctx: commands.Context, *, anime: Optional[str] = None) -> None:
        """Gère ta liste d'animes suivis.

        Utilisation:
          !track : affiche ta liste
          !track add <titre> : ajoute un anime
          !track remove <titre> : retire un anime
          !track clear : vide ta liste
        """
        if ctx.invoked_subcommand is None:
            if anime:
                await self.track_add(ctx, anime=anime)
            else:
                await self.track_list(ctx)

    @track.command(name="list")
    async def track_list(self, ctx: commands.Context) -> None:
        """Affiche ta liste d'animes suivis."""
        try:
            tracker = core.load_tracker()
            current_list = tracker.get(str(ctx.author.id), [])

            if not current_list:
                await ctx.send("📭 Tu ne suis aucun anime actuellement.\nUtilise `!track add <titre>` pour commencer.")
                return

            # Pagination pour les listes longues
            items_per_page = 10
            pages = [current_list[i:i + items_per_page]
                    for i in range(0, len(current_list), items_per_page)]

            for i, page in enumerate(pages, 1):
                embed = discord.Embed(
                    title=f"📌 Animes suivis par {ctx.author.display_name}",
                    description="\n".join(f"{idx+1}. {title}"
                                        for idx, title in enumerate(page, start=(i-1)*items_per_page)),
                    color=discord.Color.gold()
                )
                if len(pages) > 1:
                    embed.set_footer(text=f"Page {i}/{len(pages)}")
                await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur affichage liste: {e}")
            await ctx.send("❌ Une erreur s'est produite.")

    @track.command(name="add")
    async def track_add(self, ctx: commands.Context, *, anime: str) -> None:
        """Ajoute un anime à ta liste de suivi."""
        try:
            # Recherche des correspondances
            matches = await self.find_anime_matches(anime)
            if not matches:
                await ctx.send(f"❌ Aucun anime trouvé pour **{anime}**.")
                return

            # Proposition de choix si plusieurs résultats
            if len(matches) > 1:
                embed = discord.Embed(
                    title="🔍 Plusieurs résultats trouvés",
                    description="Réponds avec le numéro correspondant :",
                    color=discord.Color.blue()
                )

                for i, match in enumerate(matches, 1):
                    title = match["title"]["romaji"]
                    info = []

                    if match.get("nextAiringEpisode"):
                        info.append(f"Épisode {match['nextAiringEpisode']['episode']} à venir")
                    elif match.get("episodes"):
                        info.append(f"{match['episodes']} épisodes")

                    if match.get("status"):
                        info.append(match["status"])
                    if match.get("seasonYear"):
                        info.append(str(match["seasonYear"]))

                    details = f" ({' - '.join(info)})" if info else ""

                    embed.add_field(
                        name=f"{i}. {title}{details}",
                        value=(f"🇬🇧 {match['title']['english']}\n" if match['title']['english'] else "") +
                              (f"🇯🇵 {match['title']['native']}" if match['title']['native'] else ""),
                        inline=False
                    )

                choice_msg = await ctx.send(embed=embed)

                try:
                    msg = await self.bot.wait_for(
                        "message",
                        timeout=30.0,
                        check=lambda m: (m.author == ctx.author and
                                       m.channel == ctx.channel and
                                       m.content.isdigit() and
                                       1 <= int(m.content) <= len(matches))
                    )
                    selected = matches[int(msg.content) - 1]
                except asyncio.TimeoutError:
                    await ctx.send("⏰ Temps écoulé, aucun anime ajouté.")
                    return
            else:
                selected = matches[0]

            # Vérification des doublons
            title = selected["title"]["romaji"]
            tracker = core.load_tracker()
            uid = str(ctx.author.id)
            current_list = tracker.setdefault(uid, [])

            # Vérification avec normalisation
            normalized = core.normalize(title)
            for existing in current_list:
                if core.normalize(existing) == normalized:
                    await ctx.send(f"⚠️ Tu suis déjà **{existing}**.")
                    return

            # Ajout de l'anime
            current_list.append(title)
            tracker[uid] = current_list
            core.save_tracker(tracker)

            embed = discord.Embed(
                title="✅ Anime ajouté",
                description=f"**{title}** a été ajouté à ta liste de suivi.",
                color=discord.Color.green()
            )

            # Ajout des informations supplémentaires
            info = []
            if selected.get("nextAiringEpisode"):
                info.append(f"• Prochain : Épisode {selected['nextAiringEpisode']['episode']}")
            if selected.get("episodes"):
                info.append(f"• Épisodes : {selected['episodes']}")
            if selected.get("status"):
                info.append(f"• Statut : {selected['status']}")
            if info:
                embed.add_field(name="Informations", value="\n".join(info), inline=False)

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur ajout anime: {e}")
            await ctx.send("❌ Une erreur s'est produite.")

    @track.command(name="remove")
    async def track_remove(self, ctx: commands.Context, *, anime: str) -> None:
        """Retire un anime de ta liste de suivi."""
        try:
            tracker = core.load_tracker()
            uid = str(ctx.author.id)
            current_list = tracker.get(uid, [])

            # Recherche avec normalisation
            normalized_search = core.normalize(anime)
            matches = []

            for existing in current_list:
                if normalized_search in core.normalize(existing):
                    matches.append(existing)

            if not matches:
                await ctx.send(f"❌ Aucun anime trouvé pour **{anime}** dans ta liste.")
                return

            if len(matches) > 1:
                # Plusieurs correspondances trouvées
                embed = discord.Embed(
                    title="🔍 Plusieurs correspondances trouvées",
                    description="Réponds avec le numéro à retirer :",
                    color=discord.Color.blue()
                )

                for i, title in enumerate(matches, 1):
                    embed.add_field(name=f"{i}. {title}", value="‎", inline=False)

                await ctx.send(embed=embed)

                try:
                    msg = await self.bot.wait_for(
                        "message",
                        timeout=30.0,
                        check=lambda m: (m.author == ctx.author and
                                       m.channel == ctx.channel and
                                       m.content.isdigit() and
                                       1 <= int(m.content) <= len(matches))
                    )
                    to_remove = matches[int(msg.content) - 1]
                except asyncio.TimeoutError:
                    await ctx.send("⏰ Temps écoulé, aucun anime retiré.")
                    return
            else:
                to_remove = matches[0]

            current_list.remove(to_remove)
            tracker[uid] = current_list
            core.save_tracker(tracker)

            embed = discord.Embed(
                title="✅ Anime retiré",
                description=f"**{to_remove}** a été retiré de ta liste de suivi.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur retrait anime: {e}")
            await ctx.send("❌ Une erreur s'est produite.")

    @track.command(name="clear")
    async def track_clear(self, ctx: commands.Context) -> None:
        """Vide ta liste d'animes suivis."""
        try:
            tracker = core.load_tracker()
            uid = str(ctx.author.id)

            if uid not in tracker or not tracker[uid]:
                await ctx.send("📭 Ta liste est déjà vide.")
                return

            # Demande de confirmation
            msg = await ctx.send("⚠️ Es-tu sûr de vouloir vider ta liste ? (Réponds par 'oui' ou 'non')")

            try:
                response = await self.bot.wait_for(
                    'message',
                    timeout=30.0,
                    check=lambda m: (m.author == ctx.author and
                                   m.channel == ctx.channel and
                                   m.content.lower() in ['oui', 'non'])
                )

                if response.content.lower() == 'oui':
                    tracker[uid] = []
                    core.save_tracker(tracker)
                    await ctx.send("✅ Ta liste a été vidée.")
                else:
                    await ctx.send("❌ Opération annulée.")

            except asyncio.TimeoutError:
                await ctx.send("⏰ Temps écoulé, opération annulée.")

        except Exception as e:
            logger.error(f"Erreur clear liste: {e}")
            await ctx.send("❌ Une erreur s'est produite.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tracker(bot))