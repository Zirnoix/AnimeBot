# cogs/episodes.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
from modules.image import generate_next_card

import discord
from discord.ext import commands
from discord import app_commands

from modules import core
from modules import i18n
from modules.app_cmd_locale import ui_str

LOG = logging.getLogger(__name__)
COLOR_PRIMARY = discord.Color.blurple()

# =============== Helpers DM ===============
def _resolve_cover(item: Dict[str, Any]) -> Optional[str]:
    """
    Prend la cover au BON endroit pour les items de core.get_airings_global().
    Préférence: item['media']['cover'] (déjà présent dans core.get_airings_global).
    Fallbacks tolérants si jamais le format diffère.
    """
    media = item.get("media") or {}
    # format standard (ce que renvoie get_airings_global)
    cover = media.get("cover")
    if cover:
        return cover

    # autres formats possibles
    ci = media.get("coverImage") or {}
    cover = ci.get("extraLarge") or ci.get("large")
    if cover:
        return cover

    # fallback ultime via détails si on a l'ID
    mid = media.get("id") or item.get("id")
    if mid:
        try:
            m = core.get_anime_details(int(mid)) or {}
            ci = m.get("coverImage") or {}
            return ci.get("large") or m.get("bannerImage")
        except Exception:
            pass
    return None

async def _ack_in_channel(ctx: commands.Context, text: str | None = None):
    lg = i18n.ctx_lang(ctx)
    if text is None:
        text = i18n.t("episodes.ack_dm", lg)
    try:
        if ctx.interaction:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(text, ephemeral=True)
            else:
                await ctx.interaction.followup.send(text, ephemeral=True)
        else:
            await ctx.reply(text, delete_after=5)
    except Exception:
        pass

async def _notice_dm_closed(ctx: commands.Context, reason: str | None = None):
    lg = i18n.ctx_lang(ctx)
    msg = i18n.t("episodes.dm_closed", lg)
    if reason:
        msg += f"\n`{reason}`"
    try:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.send_message(msg, ephemeral=True)
        elif ctx.interaction:
            await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.reply(msg, delete_after=12)
    except Exception:
        pass

async def _send_dm(ctx: commands.Context, content: Optional[str] = None,
                   embed: Optional[discord.Embed] = None,
                   file: Optional[discord.File] = None) -> bool:
    await _ack_in_channel(ctx)
    try:
        if embed and file:
            await ctx.author.send(content or "", embed=embed, file=file)
        elif embed:
            await ctx.author.send(content or "", embed=embed)
        elif file:
            await ctx.author.send(content or "", file=file)
        else:
            await ctx.author.send(content or "—")
        return True
    except discord.Forbidden as e:
        await _notice_dm_closed(ctx, f"{type(e).__name__}")
        return False
    except Exception as e:
        await _notice_dm_closed(ctx, f"{type(e).__name__}: {e}")
        return False

async def _send_dm_multi(ctx: commands.Context, embeds: List[discord.Embed]) -> bool:
    await _ack_in_channel(ctx)
    try:
        if not embeds:
            await ctx.author.send("—")
            return True
        # Discord limite à 10 embeds par message
        await ctx.author.send(embeds=embeds[:10])
        for i in range(10, len(embeds), 10):
            await ctx.author.send(embeds=embeds[i:i + 10])
        return True
    except discord.Forbidden as e:
        await _notice_dm_closed(ctx, f"{type(e).__name__}")
        return False
    except Exception as e:
        await _notice_dm_closed(ctx, f"{type(e).__name__}: {e}")
        return False

# =============== Helpers format ===============
def _tz():
    """Timezone préférée (modules.core.TIMEZONE si dispo), sinon Europe/Paris, sinon UTC."""
    try:
        tz = getattr(core, "TIMEZONE", None)
        if tz:
            return tz
    except Exception:
        pass
    try:
        import pytz, os
        return pytz.timezone(os.getenv("BOT_TIMEZONE", "Europe/Paris"))
    except Exception:
        return timezone.utc

def _pick_title_from_any(media_or_title: dict) -> str:
    """Accepte soit un dict media{'title':{...}}, soit un dict title{...} direct."""
    if not isinstance(media_or_title, dict):
        return "Anime"
    if "title" in media_or_title and isinstance(media_or_title["title"], dict):
        t = media_or_title["title"]
        return t.get("romaji") or t.get("english") or t.get("native") or "Anime"
    return media_or_title.get("romaji") or media_or_title.get("english") or media_or_title.get("native") or "Anime"

def _pick_title(media_title_dict_or_media: dict) -> str:
    # accepte {"title": {...}} ou directement {"romaji":...}
    t = media_title_dict_or_media.get("title", media_title_dict_or_media) or {}
    return t.get("romaji") or t.get("english") or t.get("native") or "Anime"


def _anilist_anime_url(media_id: int) -> str:
    return f"https://anilist.co/anime/{int(media_id)}"


def _md_link_title(s: str, max_len: int = 72) -> str:
    """Comme /airings all : titre dans un lien Markdown (évite [] qui cassent le rendu)."""
    t = (s or "—").replace("[", "(").replace("]", ")")
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def _chunk_lines_for_embed(lines: List[str], max_chars: int = 1020) -> List[str]:
    """Découpe en blocs ≤ ~1024 car. (limite d’un field Discord) — même logique que /airings all."""
    chunks: List[str] = []
    buf: List[str] = []
    size = 0
    for line in lines:
        add = len(line) + (1 if buf else 0)
        if buf and size + add > max_chars:
            chunks.append("\n".join(buf))
            buf = [line]
            size = len(line)
        else:
            buf.append(line)
            size += add
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _group_by_day_user(items: list[dict]) -> dict[int, list[tuple[dict, datetime]]]:
    """items issus de core.get_upcoming_episodes(username). Clés : weekday() 0=lun … 6=dim."""
    out: dict[int, list[tuple[dict, datetime]]] = {}
    tz = _tz()
    for it in items or []:
        ts = it.get("airingAt")
        if not ts:
            continue
        dt = datetime.fromtimestamp(int(ts), tz=tz)
        wd = int(dt.weekday())
        out.setdefault(wd, []).append((it, dt))
    return out


def _group_by_day(items: List[Dict[str, Any]]) -> Dict[int, List[tuple[Dict[str, Any], datetime]]]:
    tz = _tz()
    plan: Dict[int, List[tuple[Dict[str, Any], datetime]]] = {}
    for ep in items:
        ts = ep.get("airingAt")
        if not ts:
            continue
        dt = datetime.fromtimestamp(ts, tz=tz)
        wd = int(dt.weekday())
        plan.setdefault(wd, []).append((ep, dt))
    return plan

def _cover_from_anilist_id(media_id: int | None) -> str | None:
    """Récupère une cover via core.get_anime_details(id) pour /monnext si besoin."""
    if not media_id:
        return None
    try:
        m = core.get_anime_details(int(media_id)) or {}
        ci = m.get("coverImage") or {}
        return ci.get("large") or m.get("bannerImage")
    except Exception:
        return None

# =============== COG ===============
class Episodes(commands.Cog):
    """Prochains épisodes & planning (liste du serveur ou global) + commandes perso AniList."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---------- /planning (server/global via choix) ----------
    @commands.hybrid_command(
        name="planning",
        description=ui_str("slash.episodes_planning"),
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name=ui_str("slash.choice_scope_server"), value="server"),
        app_commands.Choice(name=ui_str("slash.choice_scope_global"), value="global"),
    ])
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def planning(self, ctx: commands.Context, scope: app_commands.Choice[str] = None) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        scope_val = (scope.value if scope else "server")
        lg = i18n.ctx_lang(ctx)

        try:
            all_items = core.get_airings_global(days=7, limit=250)
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            await _send_dm(ctx, content=i18n.t("episodes.err_planning", lg, detail=detail))
            return

        items = all_items
        if scope_val == "server" and ctx.guild:
            items = core.filter_airings_for_guild(ctx.guild.id, all_items)

        if not items:
            sc = i18n.t("episodes.scope_server", lg) if scope_val == "server" else i18n.t("episodes.scope_global", lg)
            await _send_dm(ctx, content=i18n.t("episodes.no_ep_week", lg, scope=sc))
            return

        genre_emoji = getattr(core, "genre_emoji", lambda g: "🎬")
        planning = _group_by_day(items)
        scope_label = i18n.t("episodes.scope_server", lg) if scope_val == "server" else i18n.t("episodes.scope_global", lg)

        embeds: List[discord.Embed] = []
        for wd in range(7):
            if wd not in planning:
                continue
            day_name = i18n.weekday_name(lg, wd)
            episodes_jour = sorted(planning[wd], key=lambda x: x[1])[:10]
            e = discord.Embed(
                title=i18n.t("episodes.planning_title", lg, day=day_name, scope=scope_label),
                color=COLOR_PRIMARY,
            )
            lines: List[str] = []
            for ep, dt in episodes_jour:
                media = ep.get("media") or ep
                heure = dt.strftime("%H:%M")
                title = _pick_title(media)
                epnum = core.format_episode_line_part(ep.get("episode"), media)
                genres = media.get("genres") or []
                emoji = genre_emoji(genres)
                mid = media.get("id")
                try:
                    mid_i = int(mid) if mid is not None else None
                except (TypeError, ValueError):
                    mid_i = None
                if mid_i is not None:
                    line1 = (
                        f"{emoji} [{_md_link_title(title)}]({_anilist_anime_url(mid_i)}) — Ep **{epnum}**"
                    )
                else:
                    line1 = f"{emoji} {title} — Ep **{epnum}**"
                lines.append(f"{line1}\n⏰ {heure}")
            chunks = _chunk_lines_for_embed(lines)
            for ci, chunk in enumerate(chunks):
                if len(chunks) == 1:
                    fname = i18n.t("episodes.field_day", lg, day=day_name, n=len(episodes_jour))
                else:
                    fname = i18n.t("episodes.field_day_part", lg, day=day_name, ci=ci + 1, parts=len(chunks))
                e.add_field(name=fname[:256], value=chunk[:1024], inline=False)
            embeds.append(e)

        await _send_dm_multi(ctx, embeds)

    # ---------- /next (serveur/global) avec IMAGE ----------
    @commands.hybrid_command(
        name="next",
        description=ui_str("slash.episodes_next"),
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name=ui_str("slash.choice_scope_server"), value="server"),
        app_commands.Choice(name=ui_str("slash.choice_scope_global"), value="global"),
    ])
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def next_cmd(self, ctx: commands.Context, scope: app_commands.Choice[str] = None) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        scope_val = (scope.value if scope else "server")
        lg = i18n.ctx_lang(ctx)

        try:
            all_items = core.get_airings_global(days=7, limit=200)
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            await _send_dm(ctx, content=i18n.t("episodes.err_next", lg, detail=detail))
            return

        items = all_items
        if scope_val == "server" and ctx.guild:
            items = core.filter_airings_for_guild(ctx.guild.id, all_items)

        now = int(datetime.now(timezone.utc).timestamp())
        item = next((it for it in items if (it.get("airingAt") or 0) > now), items[0] if items else None)

        if not item:
            sc = i18n.t("episodes.scope_server", lg) if scope_val == "server" else i18n.t("episodes.scope_global", lg)
            await _send_dm(ctx, content=i18n.t("episodes.no_next_week", lg, scope=sc))
            return

        media = item.get("media") or {}
        title = _pick_title(media)
        epnum = item.get("episode") or "?"
        ts = item.get("airingAt") or 0
        genres = media.get("genres") or []
        dt = datetime.fromtimestamp(ts, tz=_tz()) if ts else datetime.now(_tz())
        
        # ----- AVANT: core.generate_next_image(...) => rendu "noir"
        # ----- MAINTENANT: modules.image.generate_next_card(...) => même rendu que les annonces
        cover = _resolve_cover(item)

        # le template generate_next_card attend:
        #   - cover (URL)
        #   - title_romaji/title_english/title_native
        #   - episode
        #   - genres (list[str])
        #   - when (str)
        tdict = media.get("title") or {}
        when_str = (
            core.format_airing_datetime_fr(ts, "Europe/Paris")
            if ts
            else i18n.t("episodes.date_unknown", lg)
        )

        img_path = generate_next_card({
            "cover": cover,
            "title_romaji": tdict.get("romaji") or _pick_title(media),
            "title_english": tdict.get("english"),
            "title_native": tdict.get("native"),
                "episode": epnum,
                "episodes": media.get("episodes"),
                "format": media.get("format"),
                "genres": genres,
                "when": when_str,
        })

        await _send_dm(ctx, file=discord.File(img_path, filename="next.png"))


    # ---------- /monnext (perso AniList lié) ----------
    @commands.hybrid_command(
        name="monnext",
        description=ui_str("slash.episodes_monnext"),
    )
    @app_commands.describe(
        limite=ui_str("slash.episodes_monnext_limite"),
        rafraichir=ui_str("slash.episodes_monnext_rafraichir"),
    )
    @commands.cooldown(1, 12, commands.BucketType.user)
    async def monnext(self, ctx: commands.Context, limite: Optional[int] = 1, rafraichir: bool = False) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        lg = i18n.ctx_lang(ctx)
        username = core.get_linked_username(ctx.author.id)
        if not username:
            await _send_dm(ctx, content=i18n.t("episodes.not_linked", lg))
            return

        try:
            items = core.get_upcoming_episodes(username, force=rafraichir) or []
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            await _send_dm(ctx, content=i18n.t("episodes.err_monnext_fetch", lg, detail=detail))
            return

        try:
            n = max(1, min(5, int(limite or 1)))
        except Exception:
            n = 1

        items = sorted(items, key=lambda x: x.get("airingAt", 0))[:n]
        if not items:
            await _send_dm(ctx, content=i18n.t("episodes.monnext_empty", lg))
            return

        # 1) Carte image sur le premier
        first = items[0]
        tdict = first.get("title") or {}
        title = _pick_title(tdict)
        epnum = first.get("episode") or "?"
        ts = first.get("airingAt") or 0
        when_str = (
            core.format_airing_datetime_fr(ts, "Europe/Paris")
            if ts
            else i18n.t("episodes.date_unknown", lg)
        )

        cover = first.get("cover") or _cover_from_anilist_id(first.get("id"))

        # 🔁 Utilise EXACTEMENT le même builder que les annonces auto
        img_path = generate_next_card({
            "cover": cover,
            "title_romaji": tdict.get("romaji") or title,
            "title_english": tdict.get("english"),
            "title_native": tdict.get("native"),
            "episode": epnum,
            "episodes": first.get("episodes"),
            "format": first.get("format"),
            "genres": first.get("genres") or [],
            "when": when_str,
        })

        await _send_dm(ctx, file=discord.File(img_path, filename="monnext.png"))

    # ---------- /monplanning (perso) ----------
    @commands.hybrid_command(
        name="monplanning",
        description=ui_str("slash.episodes_monplanning"),
    )
    @app_commands.describe(
        rafraichir=ui_str("slash.episodes_monplanning_rafraichir"),
    )
    @commands.cooldown(1, 12, commands.BucketType.user)
    async def monplanning(self, ctx: commands.Context, rafraichir: bool = False) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        lg = i18n.ctx_lang(ctx)
        username = core.get_linked_username(ctx.author.id)
        if not username:
            await _send_dm(ctx, content=i18n.t("episodes.not_linked", lg))
            return

        try:
            items = core.get_upcoming_episodes(username, force=rafraichir) or []
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            await _send_dm(ctx, content=i18n.t("episodes.err_monplanning_fetch", lg, detail=detail))
            return

        if not items:
            await _send_dm(ctx, content=i18n.t("episodes.monplanning_empty", lg))
            return

        planning = _group_by_day_user(items)

        embeds: list[discord.Embed] = []
        for wd in range(7):
            jour_items = planning.get(wd)
            if not jour_items:
                continue

            # tri par heure
            jour_items.sort(key=lambda x: x[1])

            day_name = i18n.weekday_name(lg, wd)
            e = discord.Embed(
                title=i18n.t("episodes.monplanning_title", lg, day=day_name),
                description="",
                color=COLOR_PRIMARY,
            )
            lines: List[str] = []
            for it, dt in jour_items[:10]:
                title = _pick_title_from_any(it.get("title") or {})
                epnum = core.format_episode_line_part(it.get("episode"), it)
                heure = dt.strftime("%H:%M")
                raw_id = it.get("id")
                try:
                    mid_i = int(raw_id) if raw_id is not None else None
                except (TypeError, ValueError):
                    mid_i = None
                if mid_i is not None:
                    line1 = (
                        f"🎬 [{_md_link_title(title)}]({_anilist_anime_url(mid_i)}) — Ep **{epnum}**"
                    )
                else:
                    line1 = f"🎬 {title} — Ep **{epnum}**"
                lines.append(f"{line1}\n⏰ {heure}")
            chunks = _chunk_lines_for_embed(lines)
            for ci, chunk in enumerate(chunks):
                if len(chunks) == 1:
                    fname = i18n.t("episodes.field_mon_part", lg, day=day_name, n=len(jour_items[:10]))
                else:
                    fname = i18n.t("episodes.field_mon_part2", lg, day=day_name, ci=ci + 1, parts=len(chunks))
                e.add_field(name=fname[:256], value=chunk[:1024], inline=False)

            embeds.append(e)

        await _send_dm_multi(ctx, embeds)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Episodes(bot))
