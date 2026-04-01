"""Réponses visibles uniquement par l’auteur (slash = éphémère ; préfixe = MP ou message effacé)."""
from __future__ import annotations

import discord
from discord.ext import commands


async def send_ephemeral_or_private(
    ctx: commands.Context,
    content: str,
    *,
    delete_after: float = 15.0,
) -> None:
    """
    Slash / hybride : followup ou response éphémère.
    Préfixe : MP si possible, sinon réponse courte auto-supprimée (pas de spam salon).
    """
    itx = getattr(ctx, "interaction", None)
    if itx:
        try:
            if not itx.response.is_done():
                await itx.response.send_message(content, ephemeral=True)
            else:
                await itx.followup.send(content, ephemeral=True)
        except discord.HTTPException:
            try:
                await itx.followup.send(content, ephemeral=True)
            except Exception:
                pass
        return
    try:
        await ctx.author.send(content)
    except Exception:
        try:
            await ctx.reply(content, mention_author=False, delete_after=delete_after)
        except Exception:
            pass


async def send_prefix_cooldown(ctx: commands.Context, content: str) -> None:
    """Cooldown pour `!commande` (on_command_error — pas d’interaction)."""
    try:
        await ctx.author.send(content)
    except Exception:
        try:
            await ctx.reply(content, mention_author=False, delete_after=15.0)
        except Exception:
            pass
