"""
Anime tracker commands avec alertes MP.

Permet aux utilisateurs de suivre des animes et de recevoir une alerte
en message privé lorsque le prochain épisode est sur le point de sortir.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, List, Dict
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from modules import core
from modules.image import generate_next_card

LOG = logging.getLogger(__name__)

# Stockage anti-spam des alertes envoyées
_sent_alerts: Dict[str, int] = {}  # key: user_id|title|episode, value: timestamp

def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def _should_alert(anime: Dict[str, any], minutes_before: int) -> bool:
    airing = anime.get("airingAt")
    if not airing:
        return False
    diff = airing - _now_ts()
    target = minutes_before * 60
    return 0 <= (target - diff) <= 60


class Tracker(commands.Cog):
    """Gestion du suivi d'animes et alertes MP."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.alert_loop.start()

    def cog_unload(self):
        self.alert_loop.cancel()

    # ----------------- Commande principale -----------------

    @commands.group(name="track", invoke_without_command=True)
    async def track(self, ctx: commands.Context, *, anime: Optional[str] = None) -> None:
        """Gère ta liste d'animes suivis."""
        if ctx.invoked_subcommand is None:
            if anime:
                await self.track_add(ctx, anime=anime)
            else:
                await self.track_list(ctx)

    # ----------------- Liste -----------------

    @track.command(name="list")
    async def track_list(self, ctx: commands.Context) -> None:
        tracker = core.load_tracker()
        current_list = tracker.get(str(ctx.author.id), [])
        if not current_list:
            await ctx.send("📭 Tu ne suis aucun anime actuellement.")
            return

        items_per_page = 10
        pages = [current_list[i:i+items_per_page] for i in range(0, len(current_list), items_per_page)]

        for i, page in enumerate(pages, 1):
            embed = discord.Embed(
                title=f"📌 Animes suivis par {ctx.author.display_name}",
                description="\n".join(f"{idx+1}. {title}"
                                      for idx, title in enumerate(page, start=(i-1)*items_per_page)),
                color=discord.Color.gold()
            )
            if len(pages) > 1:
                embed.set_footer(text=f"Page {i}/{len(pages)}")
            await ctx.send(embed=embed)

    # ----------------- Ajout -----------------

    @track.command(name="add")
    async def track_add(self, ctx: commands.Context, *, anime: str) -> None:
        matches = await self.find_anime_matches(anime)
        if not matches:
            await ctx.send(f"❌ Aucun anime trouvé pour **{anime}**.")
            return

        if len(matches) > 1:
            embed = discord.Embed(
                title="🔍 Plusieurs résultats trouvés",
                description="Réponds avec le numéro correspondant :",
                color=discord.Color.blue()
            )
            for i, match in enumerate(matches, 1):
                title = match["title"]["romaji"]
                info = []
                if match.get("nextAiringEpisode"):
                    info.append(f"Épisode {match['nextAiringEpisode']['episode']} à venir")
                elif match.get("episodes"):
                    info.append(f"{match['episodes']} épisodes")
                if match.get("status"):
                    info.append(match["status"])
                if match.get("seasonYear"):
                    info.append(str(match["seasonYear"]))
                details = f" ({' - '.join(info)})" if info else ""
                embed.add_field(
                    name=f"{i}. {title}{details}",
                    value=(f"🇬🇧 {match['title']['english']}\n" if match['title']['english'] else "") +
                          (f"🇯🇵 {match['title']['native']}" if match['title']['native'] else ""),
                    inline=False
                )
            await ctx.send(embed=embed)
            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
                                    and 1 <= int(m.content) <= len(matches)
                )
                selected = matches[int(msg.content) - 1]
            except asyncio.TimeoutError:
                await ctx.send("⏰ Temps écoulé, aucun anime ajouté.")
                return
        else:
            selected = matches[0]

        title = selected["title"]["romaji"]
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        current_list = tracker.setdefault(uid, [])

        if core.normalize(title) in [core.normalize(t) for t in current_list]:
            await ctx.send(f"⚠️ Tu suis déjà **{title}**.")
            return

        current_list.append(title)
        tracker[uid] = current_list
        core.save_tracker(tracker)
        await ctx.send(embed=discord.Embed(
            title="✅ Anime ajouté",
            description=f"**{title}** a été ajouté à ta liste.",
            color=discord.Color.green()
        ))

    # ----------------- Suppression -----------------

    @track.command(name="remove")
    async def track_remove(self, ctx: commands.Context, *, anime: str) -> None:
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        current_list = tracker.get(uid, [])
        if not current_list:
            await ctx.send("❌ Ta liste est vide.")
            return

        matches = [t for t in current_list if core.normalize(anime) in core.normalize(t)]
        if not matches:
            await ctx.send(f"❌ Aucun anime trouvé pour **{anime}**.")
            return

        if len(matches) > 1:
            embed = discord.Embed(
                title="🔍 Plusieurs correspondances trouvées",
                description="Réponds avec le numéro à retirer :",
                color=discord.Color.blue()
            )
            for i, title in enumerate(matches, 1):
                embed.add_field(name=f"{i}. {title}", value="‎", inline=False)
            await ctx.send(embed=embed)
            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
                                    and 1 <= int(m.content) <= len(matches)
                )
                to_remove = matches[int(msg.content) - 1]
            except asyncio.TimeoutError:
                await ctx.send("⏰ Temps écoulé, aucun anime retiré.")
                return
        else:
            to_remove = matches[0]

        current_list.remove(to_remove)
        tracker[uid] = current_list
        core.save_tracker(tracker)
        await ctx.send(embed=discord.Embed(
            title="✅ Anime retiré",
            description=f"**{to_remove}** a été retiré.",
            color=discord.Color.red()
        ))

    # ----------------- Clear -----------------

    @track.command(name="clear")
    async def track_clear(self, ctx: commands.Context) -> None:
        tracker = core.load_tracker()
        uid = str(ctx.author.id)
        if uid not in tracker or not tracker[uid]:
            await ctx.send("📭 Ta liste est déjà vide.")
            return

        await ctx.send("⚠️ Es-tu sûr ? (oui/non)")
        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=30.0,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                                and m.content.lower() in ["oui", "non"]
            )
            if msg.content.lower() == "oui":
                tracker[uid] = []
                core.save_tracker(tracker)
                await ctx.send("✅ Liste vidée.")
            else:
                await ctx.send("❌ Opération annulée.")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé.")

    # ----------------- Recherche AniList -----------------

    async def find_anime_matches(self, search: str) -> List[Dict]:
        query = '''
        query ($search: String) {
          Page(perPage: 5) {
            media(type: ANIME, search: $search) {
              id
              title { romaji english native }
              status
              nextAiringEpisode { episode airingAt }
              format
              episodes
              season
              seasonYear
            }
          }
        }
        '''
        try:
            result = core.query_anilist(query, {"search": search})
            return result["data"]["Page"]["media"] if result and "data" in result else []
        except Exception as e:
            LOG.error(f"Erreur recherche anime: {e}")
            return []

    # ----------------- Boucle Alertes MP -----------------

    @tasks.loop(seconds=120)
    async def alert_loop(self):
        tracker = core.load_tracker()
        for uid, animes in tracker.items():
            user = self.bot.get_user(int(uid))
            if not user:
                continue
            for title in animes:
                anime = core.get_next_airing_for_title(title)
                if not anime:
                    continue
                for m in (30, 15):
                    if _should_alert(anime, m):
                        key = f"{uid}|{title}|{anime['episode']}|{m}"
                        if _sent_alerts.get(key):
                            continue
                        img_path = generate_next_card(
                            anime,
                            out_path=f"/tmp/track_alert_{uid}.png",
                            scale=1.2,
                            padding=40
                        )
                        try:
                            await user.send(
                                f"⏰ **Alerte {m} min** pour ton anime suivi :",
                                file=discord.File(img_path, filename=f"alert_{int(_now_ts())}.png")
                            )
                            _sent_alerts[key] = _now_ts()
                        except discord.Forbidden:
                            LOG.warning(f"Impossible d'envoyer MP à {uid}")

    @alert_loop.before_loop
    async def before_alert_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tracker(bot))
