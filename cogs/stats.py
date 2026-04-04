# cogs/stats.py
from __future__ import annotations
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from modules import core
from modules import i18n
from modules.app_cmd_locale import ui_str
from modules.text_bars import pct_bar_parallelogram

# ---------- Helpers affichage ----------
def fmt_int(n: int) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)

def human_minutes_compact(m: int, lang: str) -> str:
    try:
        m = int(m or 0)
    except Exception:
        m = 0
    if m <= 0:
        return i18n.t("stats.time_dash", lang)
    h_total = m // 60
    d, h = divmod(h_total, 24)
    if d >= 2:
        return i18n.t("stats.time_days", lang, n=d)
    if d == 1:
        return i18n.t("stats.time_one_day", lang, h=h)
    return i18n.t("stats.time_hours", lang, h=h)

def score_to_color(mean: float) -> int:
    """0 -> rouge, 100 -> vert."""
    try:
        mean = max(0.0, min(float(mean or 0.0), 100.0))
    except Exception:
        mean = 0.0
    if mean <= 50:
        r = 230
        g = int(180 * (mean / 50.0))         # rouge -> jaune
    else:
        r = int(230 * (1 - (mean - 50) / 50.0))   # jaune -> vert
        g = 180 + int(75 * ((mean - 50) / 50.0))
    b = 90
    return (r << 16) + (g << 8) + b


def build_anilist_stats_embed(
    ctx: commands.Context,
    brief_user: dict,
    target: str,
    profile: dict,
    total_entries: int,
    completed: int,
    current: int,
    *,
    lang: str,
) -> discord.Embed:
    """Embed pour /mystats et /stats — champs lisibles, miniature, titre cliquable vers AniList."""
    approx = bool(profile.get("_approx"))
    prefix = "≈ " if approx else ""

    count = int(profile.get("count", 0))
    minutes = int(profile.get("minutesWatched", 0))
    mean = float(profile.get("meanScore", 0) or 0.0)
    dash = i18n.t("stats.time_dash", lang)
    fav = profile.get("favoriteGenre") or dash

    total = int(total_entries or 0)
    done_pct = 0 if total <= 0 else int(round(100 * completed / total))
    color = score_to_color(mean) if mean > 0 else 0x5865F2

    display = brief_user.get("name") or target
    note_s = f"{mean:.1f}" if mean > 0 else dash
    site_url = brief_user.get("siteUrl")
    av = brief_user.get("avatar")

    desc_lines: list[str] = []
    if approx:
        desc_lines.append(i18n.t("stats.embed_partial", lang))
        desc_lines.append("")
    if site_url:
        desc_lines.append(i18n.t("stats.embed_sheet", lang, display=display, site_url=site_url))
    else:
        desc_lines.append(i18n.t("stats.embed_user", lang, display=display))

    kw: dict = {
        "title": f"📊 {display}",
        "description": "\n".join(desc_lines) if desc_lines else None,
        "color": color,
    }
    if site_url:
        kw["url"] = site_url
    e = discord.Embed(**kw)

    if av:
        e.set_thumbnail(url=av)

    e.add_field(
        name=i18n.t("stats.field_activity", lang),
        value=i18n.t(
            "stats.activity_lines",
            lang,
            prefix=prefix,
            count=fmt_int(count),
            watch_time=human_minutes_compact(minutes, lang),
            note=note_s,
        ),
        inline=True,
    )
    e.add_field(
        name=i18n.t("stats.field_list", lang),
        value=i18n.t(
            "stats.list_lines",
            lang,
            completed=fmt_int(completed),
            current=fmt_int(current),
            total=fmt_int(total),
        ),
        inline=True,
    )
    if fav != dash:
        e.add_field(
            name=i18n.t("stats.field_fav_genre", lang),
            value=f"**{fav}**",
            inline=False,
        )

    e.add_field(
        name=i18n.t("stats.field_completion", lang),
        value=i18n.t(
            "stats.completion_bar",
            lang,
            bar=pct_bar_parallelogram(completed, total, 18),
            pct=done_pct,
        ),
        inline=False,
    )

    if not approx:
        try:
            g = profile.get("genres") or []
            g_sorted = sorted(g, key=lambda x: int(x.get("count") or 0), reverse=True)[:5]
            if g_sorted:
                total_g = sum(int(x.get("count") or 0) for x in g_sorted) or 1
                lines = []
                for x in g_sorted:
                    gn = x.get("genre") or dash
                    c = int(x.get("count") or 0)
                    p = int(round(100 * c / total_g))
                    lines.append(
                        i18n.t("stats.genre_row", lang, gn=gn, c=fmt_int(c), p=p),
                    )
                e.add_field(
                    name=i18n.t("stats.field_top_genres", lang),
                    value="\n".join(lines)[:1024],
                    inline=False,
                )
        except Exception:
            pass

    footer_parts = [i18n.t("stats.footer_requested", lang, name=ctx.author.display_name)]
    viewer_al = core.get_linked_username(ctx.author.id)
    tgt = (target or "").strip().lower()
    if viewer_al and viewer_al.lower() == tgt:
        footer_parts.append(i18n.t("stats.footer_linked_vote", lang))
    elif not viewer_al:
        footer_parts.append(i18n.t("stats.footer_link_hint", lang))
    e.set_footer(text=" · ".join(footer_parts)[:2048])
    return e


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _send(self, ctx: commands.Context,
                    content: str | None = None,
                    embed: discord.Embed | None = None,
                    ephemeral: bool = False) -> None:
        itx = getattr(ctx, "interaction", None)
        if itx:
            if itx.response.is_done():
                await itx.followup.send(content=content, embed=embed, ephemeral=ephemeral)
            else:
                await itx.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
        else:
            await ctx.send(content=content, embed=embed)

    async def _fetch_user_brief(self, name: str, *, queue_ctx: Optional[commands.Context] = None) -> dict | None:
        q = """
        query ($name: String) {
          User(name: $name) {
            name
            siteUrl
            avatar { large }
          }
        }"""
        try:
            data = await core.query_anilist_async(q, {"name": name}, queue_ctx=queue_ctx)
            u = data["data"]["User"]
            if not u:
                return None
            return {
                "name": u["name"],
                "siteUrl": u.get("siteUrl"),
                "avatar": (u.get("avatar") or {}).get("large"),
            }
        except Exception:
            return None

    # ==================== /mystats ====================
    @commands.hybrid_command(
        name="mystats",
        description=ui_str("slash.stats_mystats"),
    )
    @commands.cooldown(1, 8, commands.BucketType.user)
    @app_commands.describe(
        pseudo=ui_str("slash.stats_param_pseudo"),
        refresh=ui_str("slash.stats_param_refresh"),
    )
    async def mystats_cmd(self, ctx: commands.Context, pseudo: Optional[str] = None, refresh: bool = False):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        lg = i18n.ctx_lang(ctx)
        if pseudo:
            brief = await self._fetch_user_brief(pseudo.strip(), queue_ctx=ctx)
            if not brief:
                return await self._send(ctx, i18n.t("stats.user_not_found", lg, pseudo=pseudo), ephemeral=True)
            target = brief["name"]
            brief_user = brief
        else:
            target = core.get_linked_username(ctx.author.id)
            if not target:
                return await self._send(ctx, i18n.t("stats.not_linked", lg), ephemeral=True)
            brief_user = await self._fetch_user_brief(target, queue_ctx=ctx) or {"name": target, "siteUrl": None, "avatar": None}

        try:
            if refresh:
                profile = core.get_profile_stats(target, force=True) or {}
                total_entries = core.get_list_total_entries(target, force=True) or 0
            else:
                profile = core.get_profile_stats(target) or {}
                total_entries = core.get_list_total_entries(target) or 0
        except Exception:
            profile, total_entries = {}, 0

        completed = current = 0
        try:
            ls = core.get_or_refresh_anilist_stats(target, ttl_hours=6) or {}
            completed = int(ls.get("completed", 0))
            current = int(ls.get("current", 0))
        except Exception:
            pass

        e = build_anilist_stats_embed(
            ctx, brief_user, target, profile, total_entries, completed, current, lang=lg,
        )
        await self._send(ctx, embed=e)

    # ==================== /stats <pseudo> ====================
    @commands.hybrid_command(
        name="stats",
        description=ui_str("slash.stats_stats"),
    )
    @commands.cooldown(1, 6, commands.BucketType.user)
    @app_commands.describe(
        pseudo=ui_str("slash.stats_param_pseudo_req"),
        refresh=ui_str("slash.stats_param_refresh2"),
    )
    async def stats_pseudo(self, ctx: commands.Context, pseudo: str, refresh: Optional[bool] = False) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        lg = i18n.ctx_lang(ctx)
        brief = await self._fetch_user_brief(pseudo.strip(), queue_ctx=ctx)
        if not brief:
            return await self._send(ctx, i18n.t("stats.user_not_found", lg, pseudo=pseudo), ephemeral=True)
        target = brief["name"]

        try:
            if refresh:
                profile = core.get_profile_stats(target, force=True) or {}
                total_entries = core.get_list_total_entries(target, force=True) or 0
            else:
                profile = core.get_profile_stats(target) or {}
                total_entries = core.get_list_total_entries(target) or 0
        except Exception:
            profile, total_entries = {}, 0

        completed = current = 0
        try:
            ls = core.get_or_refresh_anilist_stats(target, ttl_hours=6) or {}
            completed = int(ls.get("completed", 0))
            current = int(ls.get("current", 0))
        except Exception:
            pass

        e = build_anilist_stats_embed(
            ctx, brief, target, profile, total_entries, completed, current, lang=lg,
        )
        await self._send(ctx, embed=e, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
