from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import discord
from discord.ext import commands, tasks

from modules import core

LOG = logging.getLogger(__name__)
DATA_PATH = "data/sent_alerts.json"   # persistance anti-doublon

# ---------- utils persistance ----------
def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def _load_sent() -> Dict[str, Dict[str, Any]]:
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_sent(data: Dict[str, Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- clés / formats ----------
def _fmt(anime: Dict[str, Any]) -> str:
    t = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    ep = anime.get("episode") or "?"
    when = core.format_airing_datetime_fr(anime.get("airingAt"), "Europe/Paris")
    return f"**{t}** — Épisode **{ep}** • {when}"

def _key(anime: Dict[str, Any], tag: str) -> str:
    t = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "?"
    e = str(anime.get("episode") or "?")
    return f"{t}|{e}|{tag}"

def _should_alert(anime: Dict[str, Any], minutes_before: int) -> bool:
    airing = anime.get("airingAt")
    if not airing:
        return False
    diff = airing - _now_ts()
    target = minutes_before * 60
    # fenêtre ~1 min autour du point visé
    return 0 <= (target - diff) <= 60

class Alerts(commands.Cog):
    """Alertes épisodes AniList — 30 min avant, dans le salon configuré via !setchannel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sent = _load_sent()
        self.check_airing.start()

    def cog_unload(self) -> None:
        self.check_airing.cancel()
        _save_sent(self.sent)

    # ----------- channel via config -----------
    async def _get_alert_channel(self) -> Optional[discord.TextChannel]:
        try:
            cfg = core.get_config() or {}
            cid = int(cfg.get("channel_id", 0))
            if not cid:
                LOG.warning("Aucun channel configuré (utilise !setchannel).")
                return None
            ch = self.bot.get_channel(cid)
            if ch is None:
                await self.bot.wait_until_ready()
                ch = self.bot.get_channel(cid)
            if isinstance(ch, discord.TextChannel):
                return ch
            LOG.warning("channel_id=%s n'est pas un salon textuel valide.", cid)
        except Exception as e:
            LOG.exception("Lecture channel_id échouée: %s", e)
        return None

    # ----------- sources d’épisodes -----------
    async def _my_next(self) -> Optional[Dict[str, Any]]:
        try:
            return core.get_my_next_airing_one()  # basé sur ANILIST_USERNAME (global du bot)
        except Exception as e:
            LOG.exception("get_my_next_airing_one failed: %s", e)
            return None

    async def _users_next(self) -> List[Dict[str, Any]]:
        """Si tu veux aussi alerter pour chaque utilisateur lié, on le garde (sinon, vide cette méthode)."""
        out: List[Dict[str, Any]] = []
        try:
            links = core.load_links()  # {discord_id_str: username}
        except Exception:
            links = {}
        for _uid, username in (links or {}).items():
            try:
                item = core.get_user_next_airing_one(username)
                if item:
                    out.append(item)
            except Exception as e:
                LOG.warning("get_user_next_airing_one(%s) err: %s", username, e)
        return out

    async def _maybe_send(self, ch: discord.TextChannel, anime: Dict[str, Any], tag: str) -> None:
        """Envoie une seule alerte si pas déjà faite."""
        k = _key(anime, tag)
        if self.sent.get(k):
            return
        try:
            await ch.send(f"⏰ **Alerte {tag} min**\n{_fmt(anime)}")
            self.sent[k] = {"at": _now_ts()}
            _save_sent(self.sent)
            LOG.info("Alerte envoyée: %s", k)
        except Exception as e:
            LOG.exception("Envoi alerte échoué: %s", e)

    # ----------- boucle: uniquement 30 minutes -----------
    @tasks.loop(seconds=120)
    async def check_airing(self):
        ch = await self._get_alert_channel()
        if not ch:
            return

        # Purge légère (clé vieilles > 14 jours)
        now = _now_ts()
        for k, v in list(self.sent.items()):
            ts = int(v.get("at", 0))
            if now - ts > 14 * 24 * 3600:
                self.sent.pop(k, None)

        # 1) Planning du bot
        mine = await self._my_next()
        if mine and _should_alert(mine, 30):
            await self._maybe_send(ch, mine, "30")

        # 2) (Optionnel) pour les utilisateurs liés
        users = await self._users_next()
        for item in users:
            if _should_alert(item, 30):
                await self._maybe_send(ch, item, "30")

    @check_airing.before_loop
    async def before(self):
        await self.bot.wait_until_ready()
        LOG.info("Alerte épisodes: boucle démarrée (30 min only).")

async def setup(bot):
    await bot.add_cog(Alerts(bot))
