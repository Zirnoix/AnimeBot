"""
!decouverte (aliases: !discover, !randomanime)
- Tirage aléatoire entre Popularité / Tendance / Score
- Slash : réponse **éphémère** (ne spam pas le salon)
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
      status
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

    async def _fetch_random_media(
        self, queue_ctx: Optional[commands.Context] = None
    ) -> Optional[tuple[Dict, str]]:
        """Retourne (media, libellé FR du tri) ou None."""
        BAD_FORMATS = {"MUSIC"}  # ajoute ici si tu veux en exclure d’autres
        for _ in range(8):  # plusieurs tentatives
            page = random.randint(1, 500)
            sort_key, sort_label = random.choice(SORTS)
            data = await core.query_anilist_async(
                QUERY, {"page": page, "sort": [sort_key]}, queue_ctx=queue_ctx
            )
            media_list = data.get("data", {}).get("Page", {}).get("media", []) or []
            if not media_list:
                continue
            media = media_list[0]
            fmt = (media.get("format") or "").upper()
            if fmt in BAD_FORMATS:
                continue  # on saute et on retente
            return media, sort_label
        return None


    @staticmethod
    def _status_fr(status: Optional[str]) -> str:
        s = (status or "").upper()
        return {
            "FINISHED": "Terminé",
            "RELEASING": "En cours",
            "NOT_YET_RELEASED": "Pas encore diffusé",
            "CANCELLED": "Annulé",
            "HIATUS": "En pause",
        }.get(s, status or "—")

    async def _build_embed(self, media: Dict, *, sort_label: str = "") -> Tuple[discord.Embed, str]:
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
        st = media.get("status")
        if st:
            infos.insert(0, f"Statut : **{self._status_fr(st)}**")

        embed = discord.Embed(
            title=f"🔎 À découvrir : {title}",
            description=f"{desc_display}\n\n{url or ''}",
            color=discord.Color.from_rgb(88, 101, 242),
        )
        if img:
            embed.set_image(url=img)
        embed.add_field(name="Genres", value=genres, inline=False)
        if infos:
            embed.add_field(name="Infos", value="\n".join(infos), inline=False)
        footer_parts = ["Source : AniList"]
        if sort_label:
            footer_parts.append(f"Tirage : {sort_label}")
        if desc_fr:
            footer_parts.append("Trad auto")
        footer_parts.append("/track add → alertes MP à la sortie d’un épisode")
        embed.set_footer(text=" · ".join(footer_parts)[:2048])
        return embed, title

    # ----------------- command -----------------

    @staticmethod
    async def _send_hybrid(ctx: commands.Context, *, content: str | None = None, embed=None, view=None) -> None:
        """Slash : message éphémère (pas de spam salon). Préfixe : message classique."""
        itx = getattr(ctx, "interaction", None)
        if itx:
            if itx.response.is_done():
                await itx.followup.send(content=content, embed=embed, view=view, ephemeral=True)
            else:
                await itx.response.send_message(content=content, embed=embed, view=view, ephemeral=True)
        else:
            await ctx.send(content=content, embed=embed, view=view)

    @commands.hybrid_command(name="decouverte", aliases=["discover", "randomanime"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decouverte(self, ctx: commands.Context):
        """Propose un anime à découvrir (mix Popularité/Tendance/Score) + boutons."""
        is_slash = bool(getattr(ctx, "interaction", None))
        await core.maybe_defer_hybrid(ctx, ephemeral=is_slash)
        try:
            if not is_slash:
                async with ctx.typing():
                    fetched = await self._fetch_random_media(ctx)
            else:
                fetched = await self._fetch_random_media(ctx)
            if not fetched:
                return await self._send_hybrid(ctx, content="❌ Impossible de récupérer une recommandation.")
            media, sort_label = fetched
            embed, _title = await self._build_embed(media, sort_label=sort_label)
        except Exception:
            return await self._send_hybrid(ctx, content="❌ Impossible de récupérer une recommandation.")

        view = DiscoverView(self, ctx.author.id, media)
        await self._send_hybrid(ctx, embed=embed, view=view)


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
            fetched = await self.cog._fetch_random_media()
            if not fetched:
                return await interaction.response.send_message("❌ Pas de nouveau résultat.", ephemeral=True)
            media, sort_label = fetched
            embed, _ = await self.cog._build_embed(media, sort_label=sort_label)
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
