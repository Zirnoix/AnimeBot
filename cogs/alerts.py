from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import discord
from discord.ext import commands, tasks

from modules import core
from modules.image import generate_next_card

LOG = logging.getLogger(__name__)

ALERT_KIND = "airing_release"


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _fmt_when(anime: Dict[str, Any]) -> str:
    return core.format_airing_datetime_fr(anime.get("airingAt"), "Europe/Paris")


def _episode_released_catchup(anime: Dict[str, Any], grace_after: int = 18 * 3600) -> bool:
    """True si la diffusion a commencé et qu’on est encore dans la fenêtre de notification."""
    airing = anime.get("airingAt")
    if not airing:
        return False
    now = _now_ts()
    if now < airing:
        return False
    return now <= airing + grace_after


def _episode_int(ep: Any) -> int:
    try:
        return int(float(ep))
    except Exception:
        return 0


class Alerts(commands.Cog):
    """
    Alertes image à la **sortie** de l’épisode dans le salon **`/setchannel`** du serveur.
    Source : **liste du serveur** (`/airings` / `airings all`), comme `/next` en mode serveur.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._legacy_migrated = False
        self.check_airing.start()

    def cog_unload(self) -> None:
        self.check_airing.cancel()

    def _migrate_legacy_channel_map(self) -> None:
        """Anciennes configs : un seul `channel_id` global → associer au serveur du salon."""
        cfg = core.get_config()
        if cfg.get("guild_alert_channels"):
            return
        cid = cfg.get("channel_id")
        if not cid:
            return
        ch = self.bot.get_channel(int(cid))
        if isinstance(ch, discord.TextChannel) and ch.guild:
            cfg.setdefault("guild_alert_channels", {})[str(ch.guild.id)] = int(cid)
            core.save_config(cfg)
            LOG.info("Alertes: migration salon %s → serveur %s", cid, ch.guild.id)

    async def _get_guild_alert_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        return await core.fetch_guild_alert_text_channel(self.bot, guild)

    async def _send_card_alert(
        self,
        ch: discord.TextChannel,
        anime: Dict[str, Any],
        header: str,
        *,
        media_id: int,
        episode_key: int,
    ) -> None:
        if media_id and core.has_been_posted(media_id, episode_key, ch.id, ALERT_KIND):
            return

        try:
            anime = dict(anime)
            anime["when"] = _fmt_when(anime)
        except Exception:
            pass

        try:
            out_path = os.path.join(
                tempfile.gettempdir(),
                f"alert_{media_id}_{episode_key}_{ch.id}.png",
            )
            # generate_next_card fait du HTTP + Pillow : ne pas bloquer l’event loop.
            img_path = await asyncio.to_thread(
                generate_next_card,
                anime,
                out_path=out_path,
                scale=1.2,
                padding=40,
            )
            # Comme /next : texte + PNG uniquement (pas d’embed). Un embed + url AniList déclenchait
            # une preview Discord imbriquée avec vignette grise ; l’image suffit (carte déjà complète).
            fn = f"sortie_{media_id}_{episode_key}.png"
            await ch.send(
                content=header,
                file=discord.File(img_path, filename=fn),
            )
            if media_id:
                core.mark_posted(media_id, episode_key, ch.id, ALERT_KIND)
        except Exception as e:
            LOG.exception("Image alert failed, fallback texte: %s", e)
            title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Anime"
            ep = anime.get("episode") or "?"
            when = _fmt_when(anime)
            await ch.send(f"{header}\n**{title}** — Épisode **{ep}** • {when}")
            if media_id:
                core.mark_posted(media_id, episode_key, ch.id, ALERT_KIND)

    @tasks.loop(seconds=60)
    async def check_airing(self):
        if not self._legacy_migrated:
            self._migrate_legacy_channel_map()
            self._legacy_migrated = True

        header = "📺 **Sortie** — l’épisode est disponible !"

        for guild in self.bot.guilds:
            ch = await self._get_guild_alert_channel(guild)
            if not ch:
                continue

            wl = core.guild_whitelist_list(guild.id)
            legacy_ids = core.guild_airings_ids(guild.id)
            if not wl and not legacy_ids:
                continue

            try:
                # get_recent_airings_for_guild → query_anilist (requests + time.sleep en retry) : hors event loop.
                items = await asyncio.to_thread(
                    core.get_recent_airings_for_guild,
                    guild.id,
                    grace_sec=18 * 3600,
                )
            except Exception as e:
                LOG.warning("get_recent_airings_for_guild(%s): %s", guild.id, e)
                continue

            for raw in items:
                flat = core.airing_item_to_card_dict(raw)
                mid = (raw.get("media") or {}).get("id")
                if not mid:
                    continue
                media_id = int(mid)
                flat["media_id"] = media_id
                ep_key = _episode_int(raw.get("episode"))

                if not _episode_released_catchup(flat):
                    continue

                await self._send_card_alert(
                    ch,
                    flat,
                    header,
                    media_id=media_id,
                    episode_key=ep_key,
                )

    @check_airing.before_loop
    async def before(self):
        await self.bot.wait_until_ready()
        LOG.info(
            "Alerte épisodes: boucle démarrée (whitelist /airings, nextAiringEpisode + créneaux passés AniList, 18 h)."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Alerts(bot))
