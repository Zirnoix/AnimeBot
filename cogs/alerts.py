from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import discord
from discord.ext import commands, tasks

from modules import core
from modules.image import generate_next_card

LOG = logging.getLogger(__name__)

DATA_PATH = "data/sent_alerts.json"  # persistance anti-doublon

# ----------------- utilitaires -----------------
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

def _key(anime: Dict[str, Any], tag: str) -> str:
    # clé unique par (titre/épisode/label)
    t = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "?"
    e = str(anime.get("episode") or "?")
    return f"{t}|{e}|{tag}"

def _should_alert(anime: Dict[str, Any], minutes_before: int, slack: int = 120) -> bool:
    """
    Déclenche si on est dans [target - slack, target + slack] autour de l’instant visé.
    slack par défaut = 120s pour tolérer la loop 60s + jitter.
    """
    airing = anime.get("airingAt")
    if not airing:
        return False
    diff = airing - _now_ts()          # secondes avant l’airing
    target = minutes_before * 60       # 0 pour “à l’heure”, 1800 pour -30 min
    return abs(diff - target) <= slack

def _fmt_when(anime: Dict[str, Any]) -> str:
    return core.format_airing_datetime_fr(anime.get("airingAt"), "Europe/Paris")

# si on n’a pas envoyé à l’heure, mais qu’on est encore dans les 10 minutes après
def _late_airing_should_fire(anime: Dict[str, Any], grace: int = 600) -> bool:
    airing = anime.get("airingAt")
    if not airing:
        return False
    diff = _now_ts() - airing  # depuis combien de secondes ça a commencé
    return 0 <= diff <= grace


class Alerts(commands.Cog):
    """Alertes épisodes AniList — image à -30 min et image à l’heure, dans le salon configuré via !setchannel."""

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
            cid = int(cfg.get("channel_id", 0)) if cfg.get("channel_id") else 0
            if not cid:
                LOG.warning("Aucun channel configuré (utilise !setchannel).")
                return None
            ch = self.bot.get_channel(cid)
            if ch is None:
                await self.bot.wait_until_ready()
                ch = self.bot.get_channel(cid)
            return ch if isinstance(ch, discord.TextChannel) else None
        except Exception as e:
            LOG.exception("Lecture channel_id échouée: %s", e)
            return None

    # ----------- sources d’épisodes -----------
    async def _my_next(self) -> Optional[Dict[str, Any]]:
        try:
            return core.get_my_next_airing_one()  # basé sur ANILIST_USERNAME
        except Exception as e:
            LOG.exception("get_my_next_airing_one failed: %s", e)
            return None

    async def _users_next(self) -> List[Dict[str, Any]]:
        """Optionnel : alerter aussi les comptes AniList liés."""
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

    # ----------- envoi image -----------
    async def _send_card_alert(self, ch: discord.TextChannel, anime: Dict[str, Any], label: str, header: str) -> None:
        """
        label = identifiant anti-doublon ("30img" ou "0img")
        header = texte au-dessus de l’image ("⏰ Alerte 30 min" / "✅ C’est l’heure !")
        """
        k = _key(anime, label)
        if self.sent.get(k):
            return

        # on enrichit le dict pour la carte si besoin
        try:
            anime = dict(anime)  # copie défensive
            anime["when"] = _fmt_when(anime)
        except Exception:
            pass

        try:
            out_path = f"/tmp/alert_{label}_{anime.get('id','x')}_{anime.get('episode','x')}.png"
            img_path = generate_next_card(
                anime,
                out_path=out_path,
                scale=1.2,
                padding=40
            )
            await ch.send(
                content=header,
                file=discord.File(img_path, filename=os.path.basename(img_path))
            )
            self.sent[k] = {"at": _now_ts()}
            _save_sent(self.sent)
        except Exception as e:
            LOG.exception("Image alert failed, fallback texte: %s", e)
            # fallback texte si la génération échoue
            title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Anime"
            ep = anime.get("episode") or "?"
            when = _fmt_when(anime)
            await ch.send(f"{header}\n**{title}** — Épisode **{ep}** • {when}")
            self.sent[k] = {"at": _now_ts()}
            _save_sent(self.sent)

    # ----------- boucle: -30 min + live (0 min), tous en image -----------
    @tasks.loop(seconds=60)
    async def check_airing(self):
        ch = await self._get_alert_channel()
        if not ch:
            return

        # purge des entrées > 14 jours
        now = _now_ts()
        for k, v in list(self.sent.items()):
            ts = int(v.get("at", 0))
            if now - ts > 14 * 24 * 3600:
                self.sent.pop(k, None)

        # 1) Planning du bot (global)
        mine = await self._my_next()
        if mine:
            if _should_alert(mine, 30, slack=120):
                await self._send_card_alert(ch, mine, "30img", "⏰ **Alerte 30 min**")
            if _should_alert(mine, 0, slack=120):
                await self._send_card_alert(ch, mine, "0img", "✅ **C’est l’heure !**")
            elif _late_airing_should_fire(mine, grace=600):
                await self._send_card_alert(ch, mine, "0img", "✅ **C’est l’heure !** (retard)")

        # 2) (Optionnel) Utilisateurs liés
        users = await self._users_next()
        for item in users:
            if _should_alert(item, 30, slack=120):
                await self._send_card_alert(ch, item, "30img", "⏰ **Alerte 30 min**")
            if _should_alert(item, 0, slack=120):
                await self._send_card_alert(ch, item, "0img", "✅ **C’est l’heure !**")
            elif _late_airing_should_fire(item, grace=600):
                await self._send_card_alert(ch, item, "0img", "✅ **C’est l’heure !** (retard)")


    @check_airing.before_loop
    async def before(self):
        await self.bot.wait_until_ready()
        LOG.info("Alerte épisodes: boucle démarrée (30 min + live).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Alerts(bot))
