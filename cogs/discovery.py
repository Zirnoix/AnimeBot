"""
!decouverte (aliases: !discover, !randomanime)
- Tirage aléatoire entre Popularité / Tendance / Score
- Slash : réponse **éphémère** (ne spam pas le salon)
- FR : traduction description (DEEPL / LibreTranslate) si configuré
- EN : titre + texte orientés AniList (anglais)
- Boutons: Encore (rafraîchir) / Ajouter au suivi (track)
"""

from __future__ import annotations
import os
import re
import random
from typing import Optional, Tuple, Dict

import discord
from discord.ext import commands

from modules import core, i18n
from modules.app_cmd_locale import ui_str

try:
    import aiohttp  # pour la traduction (HTTP)
except Exception:
    aiohttp = None

# Tri AniList → clé i18n discovery.sort_*
SORTS: list[tuple[str, str]] = [
    ("POPULARITY_DESC", "POPULARITY"),
    ("TRENDING_DESC", "TRENDING"),
    ("SCORE_DESC", "SCORE"),
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

    async def _fetch_random_media(
        self, queue_ctx: Optional[commands.Context] = None
    ) -> Optional[tuple[Dict, str]]:
        """Retourne (media, sort_id pour i18n: POPULARITY|TRENDING|SCORE) ou None."""
        BAD_FORMATS = {"MUSIC"}
        for _ in range(8):
            page = random.randint(1, 500)
            sort_key, sort_id = random.choice(SORTS)
            data = await core.query_anilist_async(
                QUERY, {"page": page, "sort": [sort_key]}, queue_ctx=queue_ctx
            )
            media_list = data.get("data", {}).get("Page", {}).get("media", []) or []
            if not media_list:
                continue
            media = media_list[0]
            fmt = (media.get("format") or "").upper()
            if fmt in BAD_FORMATS:
                continue
            return media, sort_id
        return None

    def _pick_title(self, media: Dict, *, lang: str) -> str:
        t = media.get("title") or {}
        if lang == "en":
            return (
                t.get("english")
                or t.get("romaji")
                or t.get("native")
                or i18n.t("discovery.unknown_title", lang)
            )
        return (
            t.get("romaji")
            or t.get("english")
            or t.get("native")
            or i18n.t("discovery.unknown_title", lang)
        )

    def _status_label(self, status: Optional[str], lang: str) -> str:
        s = (status or "").upper()
        key = f"discovery.status_{s}"
        out = i18n.t(key, lang)
        if out == key:
            return status or "—"
        return out

    async def _build_embed(
        self, media: Dict, *, lang: str, sort_id: str = ""
    ) -> Tuple[discord.Embed, str]:
        title = self._pick_title(media, lang=lang)
        img = (
            media.get("coverImage", {}).get("extraLarge")
            or media.get("coverImage", {}).get("large")
        )
        genres = ", ".join(media.get("genres") or []) or "—"
        score = media.get("averageScore")
        url = media.get("siteUrl")

        desc_src = _clean_html(media.get("description") or "")
        desc_translated: Optional[str] = None
        if lang == "fr":
            desc_translated = await _translate_to_fr(desc_src)
            desc_display = _shorten(desc_translated or desc_src, 420)
        else:
            desc_display = _shorten(desc_src, 420)

        infos: list[str] = []
        if media.get("episodes"):
            infos.append(
                f"{i18n.t('discovery.lbl_episodes', lang)} : **{media['episodes']}**"
            )
        if media.get("format"):
            infos.append(
                f"{i18n.t('discovery.lbl_format', lang)} : **{media['format']}**"
            )
        if media.get("seasonYear"):
            infos.append(
                f"{i18n.t('discovery.lbl_season', lang)} : **{media.get('season', '?')} {media['seasonYear']}**"
            )
        if score:
            infos.append(
                f"{i18n.t('discovery.lbl_score', lang)} : **{score}/100**"
            )
        st = media.get("status")
        if st:
            infos.insert(
                0,
                f"{i18n.t('discovery.lbl_status', lang)} : **{self._status_label(st, lang)}**",
            )

        embed = discord.Embed(
            title=i18n.t("discovery.embed_title", lang, title=title),
            description=f"{desc_display}\n\n{url or ''}",
            color=discord.Color.from_rgb(88, 101, 242),
        )
        if img:
            embed.set_image(url=img)
        embed.add_field(
            name=i18n.t("discovery.field_genres", lang),
            value=genres,
            inline=False,
        )
        if infos:
            embed.add_field(
                name=i18n.t("discovery.field_infos", lang),
                value="\n".join(infos),
                inline=False,
            )
        footer_parts = [i18n.t("discovery.footer_source", lang)]
        if sort_id:
            sort_label = i18n.t(f"discovery.sort_{sort_id}", lang)
            footer_parts.append(
                i18n.t("discovery.footer_pick", lang, sort=sort_label)
            )
        if lang == "fr" and desc_translated:
            footer_parts.append(i18n.t("discovery.footer_auto_tr", lang))
        footer_parts.append(i18n.t("discovery.footer_track", lang))
        embed.set_footer(text=" · ".join(footer_parts)[:2048])
        return embed, title

    @staticmethod
    async def _send_hybrid(
        ctx: commands.Context,
        *,
        content: str | None = None,
        embed=None,
        view=None,
    ) -> None:
        itx = getattr(ctx, "interaction", None)
        if itx:
            if itx.response.is_done():
                await itx.followup.send(
                    content=content, embed=embed, view=view, ephemeral=True
                )
            else:
                await itx.response.send_message(
                    content=content, embed=embed, view=view, ephemeral=True
                )
        else:
            await ctx.send(content=content, embed=embed, view=view)

    @commands.hybrid_command(
        name="decouverte",
        aliases=["discover", "randomanime"],
        description=ui_str("slash.discovery_decouverte"),
    )
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decouverte(self, ctx: commands.Context):
        """Propose un anime à découvrir (mix Popularité/Tendance/Score) + boutons."""
        lang = i18n.guild_lang(ctx.guild)
        is_slash = bool(getattr(ctx, "interaction", None))
        await core.maybe_defer_hybrid(ctx, ephemeral=is_slash)
        try:
            if not is_slash:
                async with ctx.typing():
                    fetched = await self._fetch_random_media(ctx)
            else:
                fetched = await self._fetch_random_media(ctx)
            if not fetched:
                return await self._send_hybrid(
                    ctx, content=i18n.t("discovery.err_fetch", lang)
                )
            media, sort_id = fetched
            embed, _title = await self._build_embed(
                media, lang=lang, sort_id=sort_id
            )
        except Exception:
            return await self._send_hybrid(
                ctx, content=i18n.t("discovery.err_fetch", lang)
            )

        view = DiscoverView(self, ctx.author.id, media, lang)
        await self._send_hybrid(ctx, embed=embed, view=view)


class DiscoverView(discord.ui.View):
    def __init__(self, cog: Discovery, author_id: int, media: Dict, lang: str):
        super().__init__(timeout=40)
        self.cog = cog
        self.author_id = author_id
        self.media = media
        self.lang = lang
        self._again = discord.ui.Button(
            label=i18n.t("discovery.btn_again", lang)[:80],
            style=discord.ButtonStyle.primary,
            row=0,
        )
        self._again.callback = self._again_cb  # type: ignore
        self.add_item(self._again)
        self._track = discord.ui.Button(
            label=i18n.t("discovery.btn_track", lang)[:80],
            style=discord.ButtonStyle.success,
            row=0,
        )
        self._track.callback = self._track_cb  # type: ignore
        self.add_item(self._track)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        lg = i18n.interaction_lang(interaction)
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                i18n.t("discovery.not_for_you", lg),
                ephemeral=True,
            )
            return False
        return True

    async def _again_cb(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        try:
            fetched = await self.cog._fetch_random_media()
            if not fetched:
                return await interaction.response.send_message(
                    i18n.t("discovery.no_result", lg),
                    ephemeral=True,
                )
            media, sort_id = fetched
            embed, _ = await self.cog._build_embed(
                media, lang=lg, sort_id=sort_id
            )
            self.media = media
            new_view = DiscoverView(
                self.cog, self.author_id, media, lg
            )
            await interaction.response.edit_message(embed=embed, view=new_view)
        except Exception:
            await interaction.response.send_message(
                i18n.t("discovery.err_refresh", lg),
                ephemeral=True,
            )

    async def _track_cb(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        try:
            title = (
                self.media.get("title", {}).get("romaji")
                or self.media.get("title", {}).get("english")
                or self.media.get("title", {}).get("native")
            )
            if not title:
                return await interaction.response.send_message(
                    i18n.t("discovery.no_title", lg),
                    ephemeral=True,
                )

            tracker = core.load_tracker()
            uid = str(interaction.user.id)
            lst = tracker.setdefault(uid, [])
            norm = core.normalize(title)
            if any(core.normalize(t) == norm for t in lst):
                return await interaction.response.send_message(
                    i18n.t("discovery.track_dup", lg),
                    ephemeral=True,
                )

            lst.append(title)
            tracker[uid] = lst
            core.save_tracker(tracker)
            await interaction.response.send_message(
                i18n.t("discovery.track_ok", lg, title=title),
                ephemeral=True,
            )
        except Exception:
            await interaction.response.send_message(
                i18n.t("discovery.track_err", lg),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Discovery(bot))
