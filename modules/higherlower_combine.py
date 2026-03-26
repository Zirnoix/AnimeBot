"""
Jaquette combinée pour Higher/Lower : deux covers AniList côte à côte (même rendu que `/higherlower`).
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any, Optional

import aiohttp
import discord
from PIL import Image

LOG = logging.getLogger(__name__)


def _cover_url(media: dict[str, Any]) -> Optional[str]:
    cov = media.get("coverImage") or {}
    return cov.get("extraLarge") or cov.get("large")


async def make_higherlower_combined_file(
    choice1: dict[str, Any],
    choice2: dict[str, Any],
    *,
    filename: str = "duel.png",
) -> Optional[discord.File]:
    """
    Télécharge les deux jaquettes et renvoie un PNG côte à côte (logique identique à `cogs/minigames` higher_lower).
    Retourne None si URL manquante ou erreur réseau / image.
    """
    url1 = _cover_url(choice1)
    url2 = _cover_url(choice2)
    if not url1 or not url2:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url1) as resp1:
                img1_bytes = await resp1.read()
            async with session.get(url2) as resp2:
                img2_bytes = await resp2.read()

        img1 = Image.open(BytesIO(img1_bytes)).convert("RGBA")
        img2 = Image.open(BytesIO(img2_bytes)).convert("RGBA")

        max_height = max(img1.height, img2.height)
        img1 = img1.resize((int(img1.width * max_height / img1.height), max_height))
        img2 = img2.resize((int(img2.width * max_height / img2.height), max_height))

        separator_width = 10
        total_width = img1.width + img2.width + separator_width
        combined = Image.new("RGBA", (total_width, max_height), (0, 0, 0, 255))
        combined.paste(img1, (0, 0))
        combined.paste(img2, (img1.width + separator_width, 0))

        buffer = BytesIO()
        combined.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename=filename)
    except Exception:
        LOG.warning("make_higherlower_combined_file failed", exc_info=True)
        return None
