"""
Simple anime discovery command.
!decouverte (aliases: !discover, !randomanime)
"""

from __future__ import annotations
import random
import textwrap

import discord
from discord.ext import commands

from modules import core

QUERY = """
query ($page: Int) {
  Page(page: $page, perPage: 1) {
    media(type: ANIME, sort: POPULARITY_DESC) {
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

def _shorten(txt: str, limit: int = 350) -> str:
    if not txt:
        return "—"
    # enlève balises html éventuelles
    clean = txt.replace("<br>", "\n").replace("<i>", "").replace("</i>", "").replace("<b>", "").replace("</b>", "")
    if len(clean) <= limit:
        return clean
    return clean[:limit].rsplit(" ", 1)[0] + "…"

class Discovery(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="decouverte", aliases=["discover", "randomanime"])
    async def decouverte(self, ctx: commands.Context):
        """Propose un anime à découvrir (populaire/trending)."""
        # Affiche "en train d'écrire..." pendant tout le boulot
        async with ctx.typing():
            # page aléatoire (élargit un peu)
            page = random.randint(1, 500)

            # IMPORTANT: query_anilist est synchrone -> on la met hors event loop
            try:
                import asyncio
                data = await asyncio.to_thread(core.query_anilist, QUERY, {"page": page})
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
            desc = _shorten(media.get("description") or "", 400)
            url = media.get("siteUrl")

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
                description=f"{desc}\n\n{url or ''}",
                color=discord.Color.blurple()
            )
            if img:
                embed.set_image(url=img)
            embed.add_field(name="Genres", value=genres, inline=False)
            if fields:
                embed.add_field(name="Infos", value="\n".join(fields), inline=False)

            # envoie après le bloc typing
            await ctx.send(embed=embed)
    

async def setup(bot: commands.Bot):
    await bot.add_cog(Discovery(bot))
