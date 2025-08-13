import os, re, random, textwrap
from typing import Optional
import discord
from discord.ext import commands
from modules import core

try:
    import aiohttp  # requis pour les appels HTTP asynchrones
except Exception:
    aiohttp = None

def _clean_html(txt: str) -> str:
    if not txt:
        return ""
    txt = txt.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    txt = re.sub(r"</?(i|b|em|strong)>", "", txt)
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

    # --- 1) DeepL ---
    deepl_key = os.getenv("DEEPL_API_KEY")
    if deepl_key and aiohttp:
        try:
            payload = {
                "text": [text],
                "target_lang": "FR",
            }
            headers = {"Authorization": f"DeepL-Auth-Key {deepl_key}"}
            # Free: api-free.deepl.com ; Pro: api.deepl.com
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

    # --- 2) LibreTranslate ---
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

    # Aucun provider dispo
    return None

class Discovery(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="decouverte", aliases=["discover", "randomanime"])
    async def decouverte(self, ctx: commands.Context):
        """Propose un anime à découvrir (populaire/trending)."""
        async with ctx.typing():
            page = random.randint(1, 500)
            sort = random.choice(SORTS)

            # core.query_anilist est synchrone -> on l’exécute hors boucle
            try:
                import asyncio
                data = await asyncio.to_thread(core.query_anilist, QUERY, {"page": page, "sort": [sort]})
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

            # --- Traduction FR si possible ---
            desc_fr = await _translate_to_fr(desc_en)
            desc_display = _shorten(desc_fr or desc_en, 420)

            fields = []
            if media.get("episodes"):
                fields.append(f"Épisodes : **{media['episodes']}**")
            if media.get("format"):
                fields.append(f"Format : **{media['format']}**")
            if media.get("seasonYear"):
                fields.append(f"Saison : **{media.get('season','?')} {media['seasonYear']}**")
            if score:
                fields.append(f"Score moyen : **{score}/100**")

            embed = discord.Embed(
                title=f"🔎 À découvrir : {title}",
                description=f"{desc_display}\n\n{url or ''}",
                color=discord.Color.blurple()
            )
            if img:
                embed.set_image(url=img)
            embed.add_field(name="Genres", value=genres, inline=False)
            if fields:
                embed.add_field(name="Infos", value="\n".join(fields), inline=False)
            embed.set_footer(text=f"Source : AniList • Tri : { 'Popularité' if sort=='POPULARITY_DESC' else 'Tendance' }")

            await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Discovery(bot))
