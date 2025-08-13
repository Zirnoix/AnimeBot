"""
!decouverte (aliases: !discover, !randomanime)
- Pioche au hasard entre Popularité / Tendance / Score
- Traduit la description en FR si DEEPL_API_KEY ou LIBRETRANSLATE_URL est défini
"""

from __future__ import annotations
import os
import re
import random
import asyncio
from typing import Optional

import discord
from discord.ext import commands

from modules import core

try:
    import aiohttp  # pour la traduction (HTTP)
except Exception:
    aiohttp = None

# Tri (clé AniList, étiquette FR)
SORTS = [
    ("POPULARITY_DESC", "Popularité"),
    ("TRENDING_DESC",   "Tendance"),
    ("SCORE_DESC",      "Score"),
]

QUERY = """
query ($page: Int, $sort: [MediaSort]) {
  Page(page: $page, perPage: 1) {
    media(type: ANIME, sort: $sort) {
      id
      title { romaji english native }
      coverImage { large extraLarge color }
      genres
      episodes
      format
      season
      seasonYear
      averageScore
      description(asHtml: false)
      siteUrl
    }
  }
}
"""

def _clean_html(txt: str) -> str:
    if not txt:
        return ""
    txt = txt.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    txt = re.sub(r"</?(i|b|em|strong|u)>", "", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    return txt.strip()

def _shorten(txt: str, limit: int = 420) -> str:
    if not txt:
        return "—"
    if len(txt) <= limit:
        return txt
    cut = txt[:limit].rsplit(" ", 1)[0]
    return cut + "…"

async def _translate_to_fr(text: str) -> Optional[str]:
    """Essaie DeepL puis LibreTranslate. Retourne None si indisponible."""
    if not text:
        return None

    # 1) DeepL
    deepl_key = os.getenv("DEEPL_API_KEY")
    if deepl_key and aiohttp:
        try:
            headers = {"Authorization": f"DeepL-Auth-Key {deepl_key}"}
            payload = {"text": [text], "target_lang": "FR"}
            deepl_url = os.getenv("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")
            async with aiohttp.ClientSession() as sess:
                async with sess.post(deepl_url, data=payload, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tr = (data.get("translations") or [{}])[0].get("text")
                        if tr:
                            return tr
        except Exception:
            pass

    # 2) LibreTranslate
    lt_url = os.getenv("LIBRETRANSLATE_URL")
    if lt_url and aiohttp:
        try:
            api_key = os.getenv("LIBRETRANSLATE_API_KEY")
            payload = {"q": text, "source": "auto", "target": "fr", "format": "text"}
            if api_key:
                payload["api_key"] = api_key
            endpoint = lt_url.rstrip("/") + "/translate"
            async with aiohttp.ClientSession() as sess:
                async with sess.post(endpoint, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tr = data.get("translatedText")
                        if tr:
                            return tr
        except Exception:
            pass

    return None


class Discovery(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="decouverte", aliases=["discover", "randomanime"])
    async def decouverte(self, ctx: commands.Context):
        """Propose un anime à découvrir (mix Popularité/Tendance/Score)."""
        async with ctx.typing():
            page = random.randint(1, 500)
            sort_key, sort_label = random.choice(SORTS)

            # core.query_anilist est synchrone -> joue hors event loop
            try:
                data = await asyncio.to_thread(core.query_anilist, QUERY, {"page": page, "sort": [sort_key]})
                media_list = data.get("data", {}).get("Page", {}).get("media", []) or []
                if not media_list:
                    raise ValueError("No media returned")
                media = media_list[0]
            except Exception:
                return await ctx.send("❌ Impossible de récupérer une recommandation.")

            title = (
                media.get("title", {}).get("romaji")
                or media.get("title", {}).get("english")
                or media.get("title", {}).get("native")
                or "Titre inconnu"
            )
            img = (
                media.get("coverImage", {}).get("extraLarge")
                or media.get("coverImage", {}).get("large")
            )
            genres = ", ".join(media.get("genres") or []) or "—"
            score = media.get("averageScore")
            desc_en = _clean_html(media.get("description") or "")
            url = media.get("siteUrl")

            # Traduction FR si possible
            desc_fr = await _translate_to_fr(desc_en)
            desc_display = _shorten(desc_fr or desc_en, 420)

            infos = []
            if media.get("episodes"):
                infos.append(f"Épisodes : **{media['episodes']}**")
            if media.get("format"):
                infos.append(f"Format : **{media['format']}**")
            if media.get("seasonYear"):
                infos.append(f"Saison : **{media.get('season','?')} {media['seasonYear']}**")
            if score:
                infos.append(f"Score moyen : **{score}/100**")

            embed = discord.Embed(
                title=f"🔎 À découvrir : {title}",
                description=f"{desc_display}\n\n{url or ''}",
                color=discord.Color.blurple()
            )
            if img:
                embed.set_image(url=img)
            embed.add_field(name="Genres", value=genres, inline=False)
            if infos:
                embed.add_field(name="Infos", value="\n".join(infos), inline=False)
            footer = f"Source : AniList • Tri : {sort_label}"
            if desc_fr:
                footer += " • Trad auto"
            embed.set_footer(text=footer)

            await ctx.send(embed=embed)

    # Test de traduction rapide
    @commands.command(name="trtest")
    @commands.is_owner()
    async def trtest(self, ctx: commands.Context, *, texte: str):
        """Test de traduction EN->FR (DeepL/LibreTranslate)."""
        tr = await _translate_to_fr(texte)
        if tr:
            await ctx.send(f"**FR :** {tr}")
        else:
            await ctx.send("❌ Pas de service de traduction dispo (DEEPL_API_KEY ou LIBRETRANSLATE_URL manquant).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Discovery(bot))
