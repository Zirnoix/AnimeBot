# cogs/stats.py
from __future__ import annotations
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from modules import core

# ---------- Helpers affichage ----------
def fmt_int(n: int) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)

def human_minutes_compact(m: int) -> str:
    try:
        m = int(m or 0)
    except Exception:
        m = 0
    if m <= 0:
        return "—"
    h_total = m // 60
    d, h = divmod(h_total, 24)
    if d >= 2:
        return f"{d} j"
    if d == 1:
        return f"1 j {h} h"
    return f"{h} h"

def bar_txt(current: int, total: int, width: int = 18) -> str:
    total = max(1, int(total or 1))
    cur = max(0, min(int(current or 0), total))
    filled = int(round(width * cur / total))
    return "▰" * filled + "▱" * (width - filled)

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
) -> discord.Embed:
    """Embed pour /mystats et /stats — champs lisibles, miniature, titre cliquable vers AniList."""
    approx = bool(profile.get("_approx"))
    prefix = "≈ " if approx else ""

    count = int(profile.get("count", 0))
    minutes = int(profile.get("minutesWatched", 0))
    mean = float(profile.get("meanScore", 0) or 0.0)
    fav = profile.get("favoriteGenre") or "—"

    total = int(total_entries or 0)
    done_pct = 0 if total <= 0 else int(round(100 * completed / total))
    color = score_to_color(mean) if mean > 0 else 0x5865F2

    display = brief_user.get("name") or target
    note_s = f"{mean:.1f}" if mean > 0 else "—"
    site_url = brief_user.get("siteUrl")
    av = brief_user.get("avatar")

    desc_lines: list[str] = []
    if approx:
        desc_lines.append("ℹ️ Profil **partiel** : chiffres **approximatifs** (source liste).")
        desc_lines.append("")
    if site_url:
        desc_lines.append(f"🔗 Fiche · [**{display}**]({site_url})")
    else:
        desc_lines.append(f"👤 **{display}**")

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
        name="🎬 Activité",
        value=(
            f"• **{prefix}{fmt_int(count)}** titres (comptés)\n"
            f"• **{prefix}{human_minutes_compact(minutes)}** de visionnage\n"
            f"• **{prefix}{note_s}**/100 note moyenne"
        ),
        inline=True,
    )
    e.add_field(
        name="📚 Liste",
        value=(
            f"• **{fmt_int(completed)}** terminés\n"
            f"• **{fmt_int(current)}** en cours\n"
            f"• **{fmt_int(total)}** entrées au total"
        ),
        inline=True,
    )
    if fav != "—":
        e.add_field(
            name="❤️ Genre favori (profil)",
            value=f"**{fav}**",
            inline=False,
        )

    e.add_field(
        name="📈 Complétion (terminés / entrées)",
        value=f"{bar_txt(completed, total)} **{done_pct}%**",
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
                    gn = x.get("genre") or "—"
                    c = int(x.get("count") or 0)
                    p = int(round(100 * c / total_g))
                    lines.append(f"▸ **{gn}** · {fmt_int(c)} · _{p}%_")
                e.add_field(name="🎭 Top genres (sur ton profil)", value="\n".join(lines)[:1024], inline=False)
        except Exception:
            pass

    footer_parts = [f"Demandé par {ctx.author.display_name}"]
    viewer_al = core.get_linked_username(ctx.author.id)
    tgt = (target or "").strip().lower()
    if viewer_al and viewer_al.lower() == tgt:
        footer_parts.append("Compte lié · 💡 Soutiens AnimeBot avec **`/vote`** (Top.gg)")
    elif not viewer_al:
        footer_parts.append("/linkanilist pour /mystats sans pseudo, récaps MP, /monnext…")
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
        description="Affiche tes stats AniList (ou celles d’un pseudo si fourni)."
    )
    @commands.cooldown(1, 8, commands.BucketType.user)
    @app_commands.describe(
        pseudo="Pseudo AniList (optionnel)",
        refresh="Forcer une mise à jour immédiate"
    )
    async def mystats_cmd(self, ctx: commands.Context, pseudo: Optional[str] = None, refresh: bool = False):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        if pseudo:
            brief = await self._fetch_user_brief(pseudo.strip(), queue_ctx=ctx)
            if not brief:
                return await self._send(ctx, f"❌ Utilisateur AniList **{pseudo}** introuvable.", ephemeral=True)
            target = brief["name"]
            brief_user = brief
        else:
            target = core.get_linked_username(ctx.author.id)
            if not target:
                return await self._send(ctx, "🔗 Tu n’as pas lié ton compte AniList. Utilise **/linkanilist <pseudo>**.", ephemeral=True)
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

        e = build_anilist_stats_embed(ctx, brief_user, target, profile, total_entries, completed, current)
        await self._send(ctx, embed=e)

    # ==================== /stats <pseudo> ====================
    @commands.hybrid_command(
        name="stats",
        description="Stats AniList d’un pseudo (profil + liste)."
    )
    @commands.cooldown(1, 6, commands.BucketType.user)
    @app_commands.describe(
        pseudo="Pseudo AniList (respecte la casse si possible)",
        refresh="Forcer une mise à jour live"
    )
    async def stats_pseudo(self, ctx: commands.Context, pseudo: str, refresh: Optional[bool] = False) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        brief = await self._fetch_user_brief(pseudo.strip(), queue_ctx=ctx)
        if not brief:
            return await self._send(ctx, f"❌ Utilisateur AniList **{pseudo}** introuvable.", ephemeral=True)
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

        e = build_anilist_stats_embed(ctx, brief, target, profile, total_entries, completed, current)
        await self._send(ctx, embed=e, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
