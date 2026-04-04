from __future__ import annotations

import asyncio
import discord
from discord.ext import commands

from modules import core, i18n


def _resolve_username(member: discord.Member | None) -> str | None:
    if member is None:
        return None
    try:
        return core.get_linked_anilist(member.id)
    except Exception:
        return None


async def _respond(ctx: commands.Context, *, content: str | None = None, embed: discord.Embed | None = None) -> None:
    """Répond proprement en slash (avec/ sans defer) ou en préfixe."""
    itx = getattr(ctx, "interaction", None)
    if itx:
        if itx.response.is_done():
            await itx.followup.send(content=content, embed=embed)
        else:
            await itx.response.send_message(content=content, embed=embed)
        return
    await ctx.reply(content=content, embed=embed)


class AniListAdmin(commands.Cog):
    """Commandes admin pour (re)sync AniList."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="anilist_sync", description="(Admin) Rafraîchit le cache AniList")
    @commands.cooldown(1, 60, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def anilist_sync(
        self,
        ctx: commands.Context,
        target: discord.Member | None = None,
        username: str | None = None,
        all: bool = False,
        force: bool = False,
        ttl_hours: int = 12,
    ) -> None:
        lg = i18n.ctx_lang(ctx)
        itx = getattr(ctx, "interaction", None)
        if itx and not itx.response.is_done():
            await itx.response.defer(thinking=True)

        ttl = max(1, int(ttl_hours))

        if all:
            usernames = getattr(core, "get_linked_anilist_usernames_bulk", lambda: [])() or []
            if not usernames:
                return await _respond(ctx, content=i18n.t("admin_anilist.sync_none", lg))
            ok = 0
            for name in usernames:
                try:
                    if force:
                        core.force_refresh_anilist_stats(name)
                        core.force_refresh_anilist_profile(name)
                    else:
                        core.get_or_refresh_anilist_stats(name, ttl_hours=ttl)
                        core.get_or_refresh_anilist_profile(name, ttl_hours=ttl)
                    ok += 1
                except Exception:
                    pass
                await asyncio.sleep(1.0)
            return await _respond(
                ctx,
                content=i18n.t("admin_anilist.sync_done", lg, ok=ok, total=len(usernames)),
            )

        if username:
            name = username.strip()
        else:
            name = _resolve_username(target) if target else _resolve_username(ctx.author)

        if not name:
            return await _respond(ctx, content=i18n.t("admin_anilist.no_user", lg))

        try:
            if force:
                counts = core.force_refresh_anilist_stats(name) or {}
                profile = core.force_refresh_anilist_profile(name) or {}
            else:
                counts = core.get_or_refresh_anilist_stats(name, ttl_hours=ttl) or {}
                profile = core.get_or_refresh_anilist_profile(name, ttl_hours=ttl) or {}
        except Exception:
            counts, profile = {}, {}

        completed = int(counts.get("completed", 0))
        current = int(counts.get("current", 0))
        total = int(counts.get("total_entries", 0))

        prof_count = int(profile.get("count", 0))
        prof_mean = float(profile.get("meanScore", 0) or 0.0)
        prof_genre = str(profile.get("favoriteGenre", "—"))

        e = discord.Embed(title=i18n.t("admin_anilist.embed_title", lg), color=discord.Color.blurple())
        e.add_field(name=i18n.t("admin_anilist.field_user", lg), value=name, inline=False)

        e.add_field(name=i18n.t("admin_anilist.f_completed", lg), value=str(completed), inline=True)
        e.add_field(name=i18n.t("admin_anilist.f_current", lg), value=str(current), inline=True)
        e.add_field(name=i18n.t("admin_anilist.f_total", lg), value=str(total), inline=True)

        e.add_field(name=i18n.t("admin_anilist.f_prof", lg), value=str(prof_count), inline=True)
        e.add_field(name=i18n.t("admin_anilist.f_mean", lg), value=f"{prof_mean:.1f}", inline=True)
        e.add_field(name=i18n.t("admin_anilist.f_genre", lg), value=prof_genre, inline=True)

        e.set_footer(
            text=i18n.t("admin_anilist.footer_force", lg)
            if force
            else i18n.t("admin_anilist.footer_ttl", lg, ttl=ttl)
        )
        await _respond(ctx, embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AniListAdmin(bot))
