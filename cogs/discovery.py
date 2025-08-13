"""
!decouverte (aliases: !discover, !randomanime)
- Tirage aléatoire entre Popularité / Tendance / Score
- Traduit la description en FR si DEEPL_API_KEY ou LIBRETRANSLATE_URL est défini
- Boutons: Encore (rafraîchir) / Ajouter au suivi (track)
"""

from __future__ import annotations
import os
import re
import random
import asyncio
from typing import Optional, Tuple, Dict

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
    media(type: ANIME, sort: $sort, isAdult: false) {
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

    # ----------------- helpers -----------------

    async def _fetch_random_media(self) -> Optional[Dict]:
        page = random.randint(1, 500)
        sort_key, _ = random.choice(SORTS)
        data = await asyncio.to_thread(core.query_anilist, QUERY, {"page": page, "sort": [sort_key]})
        media_list = data.get("data", {}).get("Page", {}).get("media", []) or []
        return media_list[0] if media_list else None

    async def _build_embed(self, media: Dict) -> Tuple[discord.Embed, str]:
        sort_label = None  # on ne l’affiche plus ici, pas critique
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
        url = media.get("siteUrl")

        desc_src = _clean_html(media.get("description") or "")
        desc_fr = await _translate_to_fr(desc_src)
        desc_display = _shorten(desc_fr or desc_src, 420)

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
        footer = "Source : AniList"
        if desc_fr:
            footer += " • Trad auto"
        embed.set_footer(text=footer)
        return embed, title

    # ----------------- command -----------------

    @commands.command(name="decouverte", aliases=["discover", "randomanime"])
    async def decouverte(self, ctx: commands.Context):
        """Propose un anime à découvrir (mix Popularité/Tendance/Score) + boutons."""
        async with ctx.typing():
            try:
                media = await self._fetch_random_media()
                if not media:
                    return await ctx.send("❌ Impossible de récupérer une recommandation.")
                embed, title = await self._build_embed(media)
            except Exception:
                return await ctx.send("❌ Impossible de récupérer une recommandation.")

        view = DiscoverView(self, ctx.author.id, media)
        await ctx.send(embed=embed, view=view)


class DiscoverView(discord.ui.View):
    def __init__(self, cog: Discovery, author_id: int, media: Dict):
        super().__init__(timeout=40)
        self.cog = cog
        self.author_id = author_id
        self.media = media  # dernier média affiché

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Cette action ne t’est pas destinée.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔁 Encore une", style=discord.ButtonStyle.primary)
    async def again(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            media = await self.cog._fetch_random_media()
            if not media:
                return await interaction.response.send_message("❌ Pas de nouveau résultat.", ephemeral=True)
            embed, _ = await self.cog._build_embed(media)
            self.media = media
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            await interaction.response.send_message("❌ Erreur pendant le rafraîchissement.", ephemeral=True)

    @discord.ui.button(label="➕ Ajouter au suivi", style=discord.ButtonStyle.success)
    async def add_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            title = (
                self.media.get("title", {}).get("romaji")
                or self.media.get("title", {}).get("english")
                or self.media.get("title", {}).get("native")
            )
            if not title:
                return await interaction.response.send_message("❌ Titre introuvable.", ephemeral=True)

            tracker = core.load_tracker()
            uid = str(interaction.user.id)
            lst = tracker.setdefault(uid, [])
            norm = core.normalize(title)
            if any(core.normalize(t) == norm for t in lst):
                return await interaction.response.send_message("⚠️ Déjà dans ton suivi.", ephemeral=True)

            lst.append(title)
            tracker[uid] = lst
            core.save_tracker(tracker)
            await interaction.response.send_message(f"✅ **{title}** ajouté à ton suivi.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("❌ Impossible d’ajouter au suivi.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Discovery(bot))
