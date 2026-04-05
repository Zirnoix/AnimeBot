"""
Garde-fou avant les mini-jeux qui consomment l’API AniList : évite de lancer une partie
(ou de perdre un point quiz) quand le service est indisponible.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import discord
from discord.ext import commands

from modules import core
from modules import i18n

_CACHE_OK_UNTIL: float = 0.0
_CACHE_TTL_SEC = 45.0

_PING_QUERY = "query { Media(id: 1, type: ANIME) { id } }"


def _ping_anilist_sync() -> bool:
    try:
        j = core.query_anilist(_PING_QUERY, None)
        if not j or not isinstance(j, dict):
            return False
        if j.get("errors"):
            return False
        return (j.get("data") or {}).get("Media") is not None
    except Exception:
        return False


async def _anilist_ok(bot: discord.Client) -> bool:
    """Ping léger (avec cache court) + alignement du flag `bot.anilist_online`."""
    global _CACHE_OK_UNTIL
    if not getattr(bot, "anilist_online", True):
        return False
    now = time.monotonic()
    if now < _CACHE_OK_UNTIL:
        return True
    ok = await asyncio.to_thread(_ping_anilist_sync)
    if ok:
        _CACHE_OK_UNTIL = time.monotonic() + _CACHE_TTL_SEC
        try:
            bot.anilist_online = True
        except Exception:
            pass
        return True
    try:
        bot.anilist_online = False
    except Exception:
        pass
    return False


def _ctx_lang(ctx: Any) -> str:
    g = getattr(ctx, "guild", None)
    return i18n.guild_lang(g)


async def _send_ctx(ctx: Any, text: str) -> None:
    itx = getattr(ctx, "interaction", None)
    if itx:
        if not itx.response.is_done():
            await itx.response.send_message(text, ephemeral=True)
        else:
            ep = ctx.guild is not None
            await itx.followup.send(text, ephemeral=ep)
    else:
        await ctx.send(text)


async def ensure_anilist_for_ctx(bot: commands.Bot, ctx: Any) -> bool:
    """Contexte commande (slash ou préfixe). False = message envoyé."""
    if await _anilist_ok(bot):
        return True
    await _send_ctx(ctx, i18n.t("anilist_gate.down", _ctx_lang(ctx)))
    return False


async def ensure_anilist_for_interaction(bot: commands.Bot, interaction: discord.Interaction) -> bool:
    """Avant `defer` sur le menu /minijeux : réponse ephemeral si indisponible."""
    if await _anilist_ok(bot):
        return True
    msg = i18n.t("anilist_gate.down", i18n.interaction_lang(interaction))
    if not interaction.response.is_done():
        await interaction.response.send_message(msg, ephemeral=True)
    else:
        await interaction.followup.send(msg, ephemeral=True)
    return False
