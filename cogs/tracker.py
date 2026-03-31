"""
Anime tracker (HYBRID) avec notification MP à la **sortie** de l’épisode (pas d’alerte « X min avant »).

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

# Une seule notif par épisode : après l’heure de diffusion (pas d’alerte « X min avant »)
_RELEASE_GRACE_SEC = 18 * 3600  # fenêtre max après l’airing pour envoyer (ratrages / bot offline)


def _should_notify_episode_release(anime: Dict[str, Any]) -> bool:
    """True si l’épisode est sorti (ou vient de sortir) et qu’on est encore dans la fenêtre de rattrapage."""
    airing = anime.get("airingAt")
    if not airing:
        return False
    now = _now_ts()
    if now < airing:
        return False
    if now > airing + _RELEASE_GRACE_SEC:
        return False
        return True


class TrackClearConfirmView(discord.ui.View):
    """Confirmation (boutons) — en slash la question est éphémère."""

    def __init__(self, cog: "Tracker", author_id: int) -> None:
        super().__init__(timeout=20)
        self.cog = cog
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce menu n’est pas pour toi.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Oui, tout supprimer", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        tracker = core.load_tracker()
        uid = str(self.author_id)
        tracker[uid] = []
        core.save_tracker(tracker)
        await interaction.response.edit_message(content="✅ **Liste vidée.**", view=None)
        try:
            u = await self.cog.bot.fetch_user(self.author_id)
            await u.send("✅ Ta liste de suivi a été **complètement vidée**.")
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="Non", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="❌ **Annulé.**", view=None)
        self.stop()


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
            await self._reply(
                ctx,
                content="⚠️ Impossible de t'envoyer un MP. Active-les pour ce serveur (Confidentialité & sécurité).",
                ephemeral=True,
            )
        except Exception as e:
            LOG.warning("DM failed: %s", e)
            await self._reply(ctx, content="⚠️ Impossible d'envoyer le MP (erreur inconnue).", ephemeral=True)
        return False

    @staticmethod
    async def _try_delete_message(msg: discord.Message | None) -> None:
        if msg is None:
            return
        try:
            await msg.delete()
        except Exception:
            pass

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
        await self._maybe_defer(ctx, ephemeral=True)
        tracker = core.load_tracker()
        current_list = tracker.get(str(ctx.author.id), [])
        if not current_list:
            usage = "/track add <titre>" if ctx.interaction else "!track add <titre>"
            ok = await self._dm(ctx, content=f"📭 Tu ne suis aucun anime actuellement.\nUtilise **{usage}** pour commencer.")
            if ok and ctx.interaction:
                await self._reply(ctx, content="📬 Message envoyé en **message privé**.", ephemeral=True)
            return

        items_per_page = 10
        pages = [current_list[i:i + items_per_page] for i in range(0, len(current_list), items_per_page)]

        sent_any = False
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
            if ok:
                sent_any = True
            else:
                break

        if sent_any and ctx.interaction:
            await self._reply(ctx, content="📬 Liste envoyée en **message privé**.", ephemeral=True)

    # ----------------- Ajout -----------------

    @track.command(name="add", with_app_command=True, description="Ajoute un anime à ta liste de suivi.")
    @app_commands.describe(anime="Titre de l'anime à suivre")
    async def track_add(self, ctx: commands.Context, *, anime: str) -> None:
        await self._maybe_defer(ctx, ephemeral=True)

        matches = await self.find_anime_matches(anime, queue_ctx=ctx)
        if not matches:
            await self._reply(ctx, content=f"❌ Aucun anime trouvé pour **{anime}**.", ephemeral=True)
            return

        if len(matches) > 1:
            embed = discord.Embed(
                title="🔍 Plusieurs résultats trouvés",
                description=(
                    "Réponds avec le **numéro** correspondant **dans ce salon** (30s). "
                    "Ton message sera **supprimé** après pour éviter le spam."
                ),
                color=discord.Color.blue()
            )
            for i, match in enumerate(matches, 1):
                title = match["title"]["romaji"]
                info = []
                if match.get("nextAiringEpisode"):
                    ep_l = core.format_episode_line_part(
                        match["nextAiringEpisode"].get("episode"), match
                    )
                    info.append(f"Épisode {ep_l} à venir")
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
            if ctx.interaction:
                await self._reply(ctx, embed=embed, ephemeral=True)
            else:
                try:
                    await ctx.author.send(embed=embed)
                except discord.Forbidden:
                    await ctx.send(embed=embed)

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
                                    and 1 <= int(m.content) <= len(matches)
                )
                await self._try_delete_message(msg)
                selected = matches[int(msg.content) - 1]
            except asyncio.TimeoutError:
                if ctx.interaction:
                    await self._reply(ctx, content="⏰ Temps écoulé, aucun anime ajouté.", ephemeral=True)
                else:
                    await ctx.send("⏰ Temps écoulé, aucun anime ajouté.")
                return
        else:
            selected = matches[0]

        title = selected["title"]["romaji"]
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        current_list = tracker.setdefault(uid, [])

        if core.normalize(title) in [core.normalize(t) for t in current_list]:
            await self._reply(ctx, content=f"⚠️ Tu suis déjà **{title}**.", ephemeral=True)
            return

        current_list.append(title)
        tracker[uid] = current_list
        core.save_tracker(tracker)

        info = []
        if selected.get("nextAiringEpisode"):
            ep_l = core.format_episode_line_part(
                selected["nextAiringEpisode"].get("episode"), selected
            )
            info.append(f"• Prochain : Épisode {ep_l}")
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
        ok = await self._dm(ctx, embed=embed)
        if ok and ctx.interaction:
            await self._reply(ctx, content="📬 Détails envoyés en **message privé**.", ephemeral=True)

    # ----------------- Suppression -----------------

    @track.command(name="remove", with_app_command=True, description="Retire un anime de ta liste.")
    @app_commands.describe(anime="Titre (ou partie) de l'anime à retirer")
    async def track_remove(self, ctx: commands.Context, *, anime: str) -> None:
        await self._maybe_defer(ctx, ephemeral=True)
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        current_list = tracker.get(uid, [])
        if not current_list:
            await self._reply(ctx, content="❌ Ta liste est vide.", ephemeral=True)
            return

        matches = [t for t in current_list if core.normalize(anime) in core.normalize(t)]
        if not matches:
            await self._reply(ctx, content=f"❌ Aucun anime trouvé pour **{anime}** dans ta liste.", ephemeral=True)
            return

        if len(matches) > 1:
            embed = discord.Embed(
                title="🔍 Plusieurs correspondances trouvées",
                description=(
                    "Réponds avec le **numéro** à retirer (30s). "
                    "Ton message sera **supprimé** après."
                ),
                color=discord.Color.blue()
            )
            for i, title in enumerate(matches, 1):
                embed.add_field(name=f"{i}. {title}", value="‎", inline=False)
            if ctx.interaction:
                await self._reply(ctx, embed=embed, ephemeral=True)
            else:
                try:
                    await ctx.author.send(embed=embed)
                except discord.Forbidden:
                    await ctx.send(embed=embed)

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
                                    and 1 <= int(m.content) <= len(matches)
                )
                await self._try_delete_message(msg)
                to_remove = matches[int(msg.content) - 1]
            except asyncio.TimeoutError:
                if ctx.interaction:
                    await self._reply(ctx, content="⏰ Temps écoulé, aucun anime retiré.", ephemeral=True)
                else:
                    await ctx.send("⏰ Temps écoulé, aucun anime retiré.")
                return
        else:
            to_remove = matches[0]

        current_list.remove(to_remove)
        tracker[uid] = current_list
        core.save_tracker(tracker)

        ok = await self._dm(ctx, content=f"✅ **{to_remove}** a été retiré de ta liste.")
        if ok and ctx.interaction:
            await self._reply(ctx, content="📬 Confirmation envoyée en **message privé**.", ephemeral=True)

    # ----------------- Clear -----------------

    @track.command(name="clear", with_app_command=True, description="Vide entièrement ta liste de suivi.")
    async def track_clear(self, ctx: commands.Context) -> None:
        await self._maybe_defer(ctx, ephemeral=True)
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        if uid not in tracker or not tracker[uid]:
            ok = await self._dm(ctx, content="📭 Ta liste est déjà vide.")
            if ok and ctx.interaction:
                await self._reply(ctx, content="📬 Message envoyé en **message privé**.", ephemeral=True)
            return

        view = TrackClearConfirmView(self, ctx.author.id)
        if getattr(ctx, "interaction", None):
            await self._reply(
                ctx,
                content="⚠️ **Supprimer toute ta liste de suivi ?**",
                view=view,
                ephemeral=True,
            )
        else:
            await ctx.send("⚠️ **Supprimer toute ta liste de suivi ?**", view=view)

    # ----------------- Recherche AniList -----------------

    async def find_anime_matches(
        self,
        search: str,
        *,
        queue_ctx: Optional[commands.Context] = None,
    ) -> List[Dict[str, Any]]:
        query = '''
        query ($search: String) {
          Page(perPage: 5) {
            media(type: ANIME, search: $search) {
              id
              title { romaji english native }
              status
              format
              nextAiringEpisode { episode airingAt }
              episodes
              season
              seasonYear
            }
          }
        }
        '''
        try:
            result = await core.query_anilist_async(query, {"search": search}, queue_ctx=queue_ctx)
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

                if not _should_notify_episode_release(anime):
                    continue

                key = f"{uid}|{title}|{anime.get('episode')}|release"
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
                    tname = anime.get("title_romaji") or anime.get("title_english") or "Anime"
                    ep_txt = core.format_episode_line_part(anime.get("episode"), anime)
                    line = f"📺 **Sortie** — **{tname}** · Épisode **{ep_txt}**"
                    if img_path:
                        await user.send(
                            line,
                            file=discord.File(img_path, filename=f"alert_{int(_now_ts())}.png")
                        )
                    else:
                        when = core.format_airing_datetime_fr(anime.get("airingAt"), "Europe/Paris")
                        await user.send(f"{line}\n🕐 {when}")
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
