"""
Anime tracker (HYBRID) avec alertes MP.

- Groupe hybrid /track (et !track)
- Sous-commandes hybrid: list, add, remove, clear
- Prompts multi-choix: on répond dans le salon (slash ou prefix), puis on attend un message
- En DM pour les confirmations / listes longues
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from discord import app_commands

from modules import core
from modules.image import generate_next_card

LOG = logging.getLogger(__name__)

# Anti-spam (mémoire vive). Si tu veux la persistance, on pourra le passer en JSON.
_sent_alerts: Dict[str, int] = {}  # key: user_id|title|episode|min, value: ts

def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def _should_alert(anime: Dict[str, Any], minutes_before: int) -> bool:
    airing = anime.get("airingAt")
    if not airing:
        return False
    diff = airing - _now_ts()
    target = minutes_before * 60
    # Fenêtre ±60s autour du point "minutes_before"
    return 0 <= (target - diff) <= 60


class Tracker(commands.Cog):
    """Gestion du suivi d'animes et alertes MP (hybrid)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.alert_loop.start()

    def cog_unload(self):
        self.alert_loop.cancel()

    # ---------- Helpers d'envoi sûrs pour HYBRID ----------

    async def _maybe_defer(self, ctx: commands.Context, ephemeral: bool = False) -> None:
        """Pour les slash: évite le 'This interaction failed' (3s)."""
        itx = getattr(ctx, "interaction", None)
        if itx and not itx.response.is_done():
            try:
                await itx.response.defer(thinking=True, ephemeral=ephemeral)
            except Exception:
                pass

    async def _reply(
        self,
        ctx: commands.Context,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = False,
        file: discord.File | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        """
        Répond proprement :
          - slash: 1ère réponse via response.send_message, sinon followup.send
          - préfixe: ctx.send
        (⚠️ on NE PASSE PAS view/file s'ils sont None → évite TypeError)
        """
        itx = getattr(ctx, "interaction", None)
    
        kwargs = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if file is not None:
            kwargs["file"] = file
        if view is not None:
            kwargs["view"] = view
    
        if itx:
            if itx.response.is_done():
                await itx.followup.send(ephemeral=ephemeral, **kwargs)
            else:
                await itx.response.send_message(ephemeral=ephemeral, **kwargs)
            return
    
        # mode préfixe
        await ctx.send(**kwargs)


    async def _dm(self, ctx: commands.Context, *, content: str | None = None,
                  embed: discord.Embed | None = None) -> bool:
        """MP à l’auteur, fallback public si MP fermés."""
        try:
            await ctx.author.send(content=content, embed=embed)
            return True
        except discord.Forbidden:
            await self._reply(ctx, content="⚠️ Impossible de t'envoyer un MP. Active-les pour ce serveur (Confidentialité & sécurité).")
        except Exception as e:
            LOG.warning("DM failed: %s", e)
            await self._reply(ctx, content="⚠️ Impossible d'envoyer le MP (erreur inconnue).")
        return False

    # ----------------- Groupe HYBRID -----------------

    @commands.hybrid_group(
        name="track",
        description="Gestion du tracking (AniList, suivis, alertes MP).",
        invoke_without_command=True
    )
    async def track(self, ctx: commands.Context, *, anime: Optional[str] = None) -> None:
        """Préfixe: !track [anime] → add/list. (En slash, toujours utiliser une sous-commande.)"""
        # Slash: jamais invoqué sans sous-commande.
        if ctx.invoked_subcommand is None and not ctx.interaction:
            if anime:
                await self.track_add(ctx, anime=anime)
            else:
                await self.track_list(ctx)

    # ----------------- Liste -----------------

    @track.command(name="list", with_app_command=True, description="Liste tes animes suivis (en MP).")
    async def track_list(self, ctx: commands.Context) -> None:
        tracker = core.load_tracker()
        current_list = tracker.get(str(ctx.author.id), [])
        if not current_list:
            usage = "/track add <titre>" if ctx.interaction else "!track add <titre>"
            await self._dm(ctx, content=f"📭 Tu ne suis aucun anime actuellement.\nUtilise **{usage}** pour commencer.")
            return

        items_per_page = 10
        pages = [current_list[i:i + items_per_page] for i in range(0, len(current_list), items_per_page)]

        # Envoie chaque page en MP
        for i, page in enumerate(pages, 1):
            embed = discord.Embed(
                title=f"📌 Animes suivis par {ctx.author.display_name}",
                description="\n".join(f"{idx+1}. {title}"
                                      for idx, title in enumerate(page, start=(i-1)*items_per_page)),
                color=discord.Color.gold()
            )
            if len(pages) > 1:
                embed.set_footer(text=f"Page {i}/{len(pages)}")
            ok = await self._dm(ctx, embed=embed)
            if not ok:
                break

    # ----------------- Ajout -----------------

    @track.command(name="add", with_app_command=True, description="Ajoute un anime à ta liste de suivi.")
    @app_commands.describe(anime="Titre de l'anime à suivre")
    async def track_add(self, ctx: commands.Context, *, anime: str) -> None:
        # Slash: anti-timeout
        await self._maybe_defer(ctx, ephemeral=False)

        matches = await self.find_anime_matches(anime)
        if not matches:
            await self._dm(ctx, content=f"❌ Aucun anime trouvé pour **{anime}**.")
            return

        # Choix multiples → on demande dans le salon (slash OU prefix)
        if len(matches) > 1:
            embed = discord.Embed(
                title="🔍 Plusieurs résultats trouvés",
                description="Réponds avec le **numéro** correspondant (30s) :",
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
            await self._reply(ctx, embed=embed, ephemeral=False)

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
                                    and 1 <= int(m.content) <= len(matches)
                )
                selected = matches[int(msg.content) - 1]
            except asyncio.TimeoutError:
                await self._reply(ctx, content="⏰ Temps écoulé, aucun anime ajouté.")
                return
        else:
            selected = matches[0]

        title = selected["title"]["romaji"]
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        current_list = tracker.setdefault(uid, [])

        if core.normalize(title) in [core.normalize(t) for t in current_list]:
            await self._dm(ctx, content=f"⚠️ Tu suis déjà **{title}**.")
            return

        current_list.append(title)
        tracker[uid] = current_list
        core.save_tracker(tracker)

        info = []
        if selected.get("nextAiringEpisode"):
            info.append(f"• Prochain : Épisode {selected['nextAiringEpisode']['episode']}")
        if selected.get("episodes"):
            info.append(f"• Épisodes : {selected['episodes']}")
        if selected.get("status"):
            info.append(f"• Statut : {selected['status']}")

        embed = discord.Embed(
            title="✅ Anime ajouté",
            description=f"**{title}** a été ajouté à ta liste de suivi.",
            color=discord.Color.green()
        )
        if info:
            embed.add_field(name="Informations", value="\n".join(info), inline=False)
        await self._dm(ctx, embed=embed)

    # ----------------- Suppression -----------------

    @track.command(name="remove", with_app_command=True, description="Retire un anime de ta liste.")
    @app_commands.describe(anime="Titre (ou partie) de l'anime à retirer")
    async def track_remove(self, ctx: commands.Context, *, anime: str) -> None:
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        current_list = tracker.get(uid, [])
        if not current_list:
            await self._dm(ctx, content="❌ Ta liste est vide.")
            return

        matches = [t for t in current_list if core.normalize(anime) in core.normalize(t)]
        if not matches:
            await self._dm(ctx, content=f"❌ Aucun anime trouvé pour **{anime}** dans ta liste.")
            return

        # Plusieurs correspondances → on demande dans le salon
        if len(matches) > 1:
            embed = discord.Embed(
                title="🔍 Plusieurs correspondances trouvées",
                description="Réponds avec le **numéro** à retirer (30s) :",
                color=discord.Color.blue()
            )
            for i, title in enumerate(matches, 1):
                embed.add_field(name=f"{i}. {title}", value="‎", inline=False)
            await self._reply(ctx, embed=embed, ephemeral=False)

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
                                    and 1 <= int(m.content) <= len(matches)
                )
                to_remove = matches[int(msg.content) - 1]
            except asyncio.TimeoutError:
                await self._reply(ctx, content="⏰ Temps écoulé, aucun anime retiré.")
                return
        else:
            to_remove = matches[0]

        current_list.remove(to_remove)
        tracker[uid] = current_list
        core.save_tracker(tracker)

        await self._dm(ctx, content=f"✅ **{to_remove}** a été retiré de ta liste.")

    # ----------------- Clear -----------------

    @track.command(name="clear", with_app_command=True, description="Vide entièrement ta liste de suivi.")
    async def track_clear(self, ctx: commands.Context) -> None:
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        if uid not in tracker or not tracker[uid]:
            await self._dm(ctx, content="📭 Ta liste est déjà vide.")
            return

        await self._reply(ctx, content="⚠️ Confirme la suppression complète ? (`oui`/`non`, 20s)", ephemeral=False)
        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=20.0,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ("oui", "non")
            )
        except asyncio.TimeoutError:
            await self._reply(ctx, content="⏰ Temps écoulé, opération annulée.")
            return

        if msg.content.lower() == "oui":
            tracker[uid] = []
            core.save_tracker(tracker)
            await self._dm(ctx, content="✅ Ta liste a été vidée.")
        else:
            await self._reply(ctx, content="❌ Opération annulée.")

    # ----------------- Recherche AniList -----------------

    async def find_anime_matches(self, search: str) -> List[Dict[str, Any]]:
        query = '''
        query ($search: String) {
          Page(perPage: 5) {
            media(type: ANIME, search: $search) {
              id
              title { romaji english native }
              status
              nextAiringEpisode { episode airingAt }
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
            return result["data"]["Page"]["media"] if result and "data" in result else []
        except Exception as e:
            LOG.error(f"Erreur recherche anime: {e}")
            return []

    # ----------------- Boucle Alertes MP -----------------

    @tasks.loop(seconds=120)
    async def alert_loop(self):
        tracker = core.load_tracker()
        for uid, animes in tracker.items():
            # user peut ne pas être en cache → fetch_user en fallback
            try:
                user = self.bot.get_user(int(uid)) or await self.bot.fetch_user(int(uid))
            except Exception:
                user = None
            if not user:
                continue

            for title in animes:
                anime = await asyncio.to_thread(core.get_next_airing_for_title, title)
                if not anime:
                    continue

                for m in (30, 15):
                    if not _should_alert(anime, m):
                        continue

                    key = f"{uid}|{title}|{anime.get('episode')}|{m}"
                    if _sent_alerts.get(key):
                        continue

                    # Génération de la carte (même style que !next)
                    img_path = None
                    try:
                        img_path = generate_next_card(
                            anime,
                            out_path=os.path.join(tempfile.gettempdir(), f"track_alert_{uid}.png"),
                            scale=1.2,
                            padding=40,
                        )
                    except Exception as e:
                        LOG.warning("generate_next_card failed: %s", e)

                    try:
                        if img_path:
                            await user.send(
                                f"⏰ **Alerte {m} min** pour **{anime.get('title_romaji') or anime.get('title_english') or 'Anime'}** — Épisode {anime.get('episode')}",
                                file=discord.File(img_path, filename=f"alert_{int(_now_ts())}.png")
                            )
                        else:
                            when = core.format_airing_datetime_fr(anime.get("airingAt"), "Europe/Paris")
                            await user.send(
                                f"⏰ **Alerte {m} min** — **{anime.get('title_romaji') or anime.get('title_english') or 'Anime'}** "
                                f"(Épisode {anime.get('episode')}) • {when}"
                            )
                        _sent_alerts[key] = _now_ts()
                    except discord.Forbidden:
                        LOG.warning("MP refusés par l'utilisateur %s", uid)
                    except Exception as e:
                        LOG.warning("Envoi MP échoué (%s): %s", uid, e)

    @alert_loop.before_loop
    async def before_alert_loop(self):
        await self.bot.wait_until_ready()
        LOG.info("Tracker: boucle de vérification démarrée.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tracker(bot))
