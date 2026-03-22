from __future__ import annotations

import asyncio
import discord
from discord.ext import commands

from modules import core

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
    # commande préfixe
    await ctx.reply(content=content, embed=embed)

class AniListAdmin(commands.Cog):
    """Commandes admin pour (re)sync AniList."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="anilist_sync", description="(Admin) Rafraîchit le cache AniList")
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
        """
        - Sans argument: sync l'auteur (si lié)
        - target: sync un membre lié
        - username: sync un username AniList précis
        - all: sync tous les comptes liés (rate-limit friendly)
        - force: force un refresh (ignore le TTL)
        - ttl_hours: TTL à utiliser si non-force
        """
        # Defer propre pour hybrid
        itx = getattr(ctx, "interaction", None)
        if itx and not itx.response.is_done():
            await itx.response.defer(thinking=True)

        ttl = max(1, int(ttl_hours))

        if all:
            usernames = getattr(core, "get_linked_anilist_usernames_bulk", lambda: [])() or []
            if not usernames:
                return await _respond(ctx, content="Aucun compte AniList lié trouvé.")
            ok = 0
            for name in usernames:
                try:
                    if force:
                        core.force_refresh_anilist_stats(name)
                        # 👇 NEW: refresh aussi le cache “profil”
                        core.force_refresh_anilist_profile(name)
                    else:
                        core.get_or_refresh_anilist_stats(name, ttl_hours=ttl)
                        # 👇 NEW: refresh aussi le cache “profil”
                        core.get_or_refresh_anilist_profile(name, ttl_hours=ttl)
                    ok += 1
                except Exception:
                    pass
                await asyncio.sleep(1.0)  # doux pour l’API
            return await _respond(ctx, content=f"Sync terminée : **{ok}/{len(usernames)}** comptes rafraîchis.")

        # cas 1: username explicite
        if username:
            name = username.strip()
        else:
            # cas 2: target membre ou auteur
            name = _resolve_username(target) if target else _resolve_username(ctx.author)

        if not name:
            return await _respond(ctx, content="Aucun username AniList lié/valide à synchroniser.")

        # 🔄 Rafraîchir les DEUX caches : listes + profil
        try:
            if force:
                counts  = core.force_refresh_anilist_stats(name) or {}
                profile = core.force_refresh_anilist_profile(name) or {}
            else:
                counts  = core.get_or_refresh_anilist_stats(name, ttl_hours=ttl) or {}
                profile = core.get_or_refresh_anilist_profile(name, ttl_hours=ttl) or {}
        except Exception:
            counts, profile = {}, {}

        # Champs “listes”
        completed = int(counts.get("completed", 0))
        current   = int(counts.get("current", 0))
        total     = int(counts.get("total_entries", 0))

        # Champs “profil”
        prof_count = int(profile.get("count", 0))
        prof_mean  = float(profile.get("meanScore", 0) or 0.0)
        prof_genre = str(profile.get("favoriteGenre", "—"))

        e = discord.Embed(title="AniList Sync", color=discord.Color.blurple())
        e.add_field(name="Utilisateur", value=name, inline=False)

        # Affiche les deux familles de stats pour bien vérifier
        e.add_field(name="✅ Completed (MLC)", value=str(completed), inline=True)
        e.add_field(name="📺 En cours (MLC)", value=str(current), inline=True)
        e.add_field(name="📚 Total entrées (MLC)", value=str(total), inline=True)

        e.add_field(name="🎬 Animés vus (profil)", value=str(prof_count), inline=True)
        e.add_field(name="⭐ Note moyenne", value=f"{prof_mean:.1f}", inline=True)
        e.add_field(name="🎭 Genre favori", value=prof_genre, inline=True)

        e.set_footer(text=("Force refresh" if force else f"TTL {ttl}h"))
        await _respond(ctx, embed=e)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AniListAdmin(bot))
