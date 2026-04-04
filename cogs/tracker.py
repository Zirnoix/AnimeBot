"""
Anime tracker (HYBRID) avec notification MP à la **sortie** de l’épisode (pas d’alerte « X min avant »).

- Groupe hybrid /track (slash uniquement côté utilisateurs)
- Sous-commandes : list, add, remove, clear
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
from modules import i18n
from modules.app_cmd_locale import ui_str
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

    def __init__(self, cog: "Tracker", author_id: int, lang: str) -> None:
        super().__init__(timeout=20)
        self.cog = cog
        self.author_id = author_id
        self.lang = lang
        self.confirm.label = i18n.t("tracker.clear_yes", lang)[:80]
        self.cancel.label = i18n.t("tracker.clear_no", lang)[:80]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(i18n.t("tracker.clear_not_you", self.lang), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Oui, tout supprimer", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        lg = self.lang
        tracker = core.load_tracker()
        uid = str(self.author_id)
        tracker[uid] = []
        core.save_tracker(tracker)
        await interaction.response.edit_message(content=i18n.t("tracker.clear_done", lg), view=None)
        try:
            u = await self.cog.bot.fetch_user(self.author_id)
            await u.send(i18n.t("tracker.clear_dm", lg))
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="Non", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=i18n.t("tracker.clear_cancel", self.lang), view=None)
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
                content=i18n.t("tracker.dm_forbidden", i18n.ctx_lang(ctx)),
                ephemeral=True,
            )
        except Exception as e:
            LOG.warning("DM failed: %s", e)
            await self._reply(
                ctx,
                content=i18n.t("tracker.dm_error", i18n.ctx_lang(ctx)),
                ephemeral=True,
            )
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
        description=ui_str("slash.tracker_group"),
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

    @track.command(name="list", with_app_command=True, description=ui_str("slash.track_list"))
    async def track_list(self, ctx: commands.Context) -> None:
        await self._maybe_defer(ctx, ephemeral=True)
        lg = i18n.ctx_lang(ctx)
        tracker = core.load_tracker()
        current_list = tracker.get(str(ctx.author.id), [])
        if not current_list:
            usage = "/track add <titre>" if ctx.interaction else "!track add <titre>"
            ok = await self._dm(ctx, content=i18n.t("tracker.list_empty", lg, usage=usage))
            if ok and ctx.interaction:
                await self._reply(ctx, content=i18n.t("tracker.list_sent", lg), ephemeral=True)
            return

        items_per_page = 10
        pages = [current_list[i:i + items_per_page] for i in range(0, len(current_list), items_per_page)]

        sent_any = False
        for i, page in enumerate(pages, 1):
            embed = discord.Embed(
                title=i18n.t("tracker.list_title", lg, name=ctx.author.display_name),
                description="\n".join(f"{idx+1}. {title}"
                                      for idx, title in enumerate(page, start=(i-1)*items_per_page)),
                color=discord.Color.gold()
            )
            if len(pages) > 1:
                embed.set_footer(text=i18n.t("tracker.list_footer_page", lg, cur=i, total=len(pages)))
            ok = await self._dm(ctx, embed=embed)
            if ok:
                sent_any = True
            else:
                break

        if sent_any and ctx.interaction:
            await self._reply(ctx, content=i18n.t("tracker.list_dm_confirm", lg), ephemeral=True)

    # ----------------- Ajout -----------------

    @track.command(name="add", with_app_command=True, description=ui_str("slash.track_add"))
    @app_commands.describe(anime=ui_str("slash.track_param_anime_add"))
    async def track_add(self, ctx: commands.Context, *, anime: str) -> None:
        await self._maybe_defer(ctx, ephemeral=True)
        lg = i18n.ctx_lang(ctx)

        matches = await self.find_anime_matches(anime, queue_ctx=ctx)
        if not matches:
            await self._reply(
                ctx,
                content=i18n.t("tracker.add_no_results", lg, anime=anime),
                ephemeral=True,
            )
            return

        if len(matches) > 1:
            embed = discord.Embed(
                title=i18n.t("tracker.pick_title", lg),
                description=i18n.t("tracker.pick_desc", lg),
                color=discord.Color.from_rgb(88, 101, 242),
            )
            for i, match in enumerate(matches, 1):
                title = match["title"]["romaji"]
                info = []
                if match.get("nextAiringEpisode"):
                    ep_l = core.format_episode_line_part(
                        match["nextAiringEpisode"].get("episode"), match
                    )
                    info.append(i18n.t("tracker.field_ep_upcoming", lg, ep=ep_l))
                elif match.get("episodes"):
                    info.append(i18n.t("tracker.field_episodes", lg, n=match["episodes"]))
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
                    await self._reply(ctx, content=i18n.t("tracker.timeout_pick", lg), ephemeral=True)
                else:
                    await ctx.send(i18n.t("tracker.timeout_pick", lg))
                return
        else:
            selected = matches[0]

        title = selected["title"]["romaji"]
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        current_list = tracker.setdefault(uid, [])

        if core.normalize(title) in [core.normalize(t) for t in current_list]:
            await self._reply(ctx, content=i18n.t("tracker.already_following", lg, title=title), ephemeral=True)
            return

        current_list.append(title)
        tracker[uid] = current_list
        core.save_tracker(tracker)

        info = []
        if selected.get("nextAiringEpisode"):
            ep_l = core.format_episode_line_part(
                selected["nextAiringEpisode"].get("episode"), selected
            )
            info.append(i18n.t("tracker.detail_next", lg, ep=ep_l))
        if selected.get("episodes"):
            info.append(i18n.t("tracker.detail_eps", lg, n=selected["episodes"]))
        if selected.get("status"):
            info.append(i18n.t("tracker.detail_status", lg, status=selected["status"]))

        cover = (selected.get("coverImage") or {}).get("large")
        embed = discord.Embed(
            title=i18n.t("tracker.added_title", lg),
            description=i18n.t("tracker.added_desc", lg, title=title),
            color=discord.Color.from_rgb(67, 181, 129),
        )
        if cover:
            embed.set_thumbnail(url=cover)
        if info:
            embed.add_field(name=i18n.t("tracker.field_details", lg), value="\n".join(info), inline=False)
        ok = await self._dm(ctx, embed=embed)
        if ok and ctx.interaction:
            await self._reply(ctx, content=i18n.t("tracker.details_sent", lg), ephemeral=True)

    # ----------------- Suppression -----------------

    @track.command(name="remove", with_app_command=True, description=ui_str("slash.track_remove"))
    @app_commands.describe(anime=ui_str("slash.track_param_anime_rm"))
    async def track_remove(self, ctx: commands.Context, *, anime: str) -> None:
        await self._maybe_defer(ctx, ephemeral=True)
        lg = i18n.ctx_lang(ctx)
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        current_list = tracker.get(uid, [])
        if not current_list:
            await self._reply(ctx, content=i18n.t("tracker.remove_empty", lg), ephemeral=True)
            return

        matches = [t for t in current_list if core.normalize(anime) in core.normalize(t)]
        if not matches:
            await self._reply(ctx, content=i18n.t("tracker.remove_none", lg, anime=anime), ephemeral=True)
            return

        if len(matches) > 1:
            embed = discord.Embed(
                title=i18n.t("tracker.remove_multi_title", lg),
                description=i18n.t("tracker.remove_multi_desc", lg),
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
                    await self._reply(ctx, content=i18n.t("tracker.timeout_remove", lg), ephemeral=True)
                else:
                    await ctx.send(i18n.t("tracker.timeout_remove", lg))
                return
        else:
            to_remove = matches[0]

        current_list.remove(to_remove)
        tracker[uid] = current_list
        core.save_tracker(tracker)

        ok = await self._dm(ctx, content=i18n.t("tracker.removed_ok", lg, title=to_remove))
        if ok and ctx.interaction:
            await self._reply(ctx, content=i18n.t("tracker.remove_confirm", lg), ephemeral=True)

    # ----------------- Clear -----------------

    @track.command(name="clear", with_app_command=True, description=ui_str("slash.track_clear"))
    async def track_clear(self, ctx: commands.Context) -> None:
        await self._maybe_defer(ctx, ephemeral=True)
        lg = i18n.ctx_lang(ctx)
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        if uid not in tracker or not tracker[uid]:
            ok = await self._dm(ctx, content=i18n.t("tracker.clear_empty", lg))
            if ok and ctx.interaction:
                await self._reply(ctx, content=i18n.t("tracker.list_sent", lg), ephemeral=True)
            return

        view = TrackClearConfirmView(self, ctx.author.id, lg)
        prompt = i18n.t("tracker.clear_prompt", lg)
        if getattr(ctx, "interaction", None):
            await self._reply(
                ctx,
                content=prompt,
                view=view,
                ephemeral=True,
            )
        else:
            await ctx.send(prompt, view=view)

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
              coverImage { large }
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
                    _al = i18n.guild_lang(None)
                    line = i18n.t("tracker.alert_release", _al, title=tname, ep=ep_txt)
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
