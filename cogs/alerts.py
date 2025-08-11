import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import discord
from discord.ext import commands, tasks

from modules import core

LOG = logging.getLogger(__name__)
DATA_PATH = "data/sent_alerts.json"

# ---------- Fonctions utilitaires internes ----------

def _now_ts() -> int:
    """Retourne l'heure actuelle en timestamp UTC (secondes)."""
    return int(datetime.now(timezone.utc).timestamp())

def _load_sent() -> Dict[str, Dict[str, Any]]:
    """Charge les alertes déjà envoyées depuis le fichier JSON."""
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_sent(data: Dict[str, Dict[str, Any]]) -> None:
    """Sauvegarde les alertes déjà envoyées dans le fichier JSON."""
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _fmt(anime: Dict[str, Any]) -> str:
    """Formate un anime pour l'affichage dans le message."""
    t = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    ep = anime.get("episode") or "?"
    when = core.format_airing_datetime_fr(anime.get("airingAt"), "Europe/Paris")
    return f"**{t}** — Épisode **{ep}** • {when}"

def _key(anime: Dict[str, Any], tag: str) -> str:
    """Crée une clé unique pour éviter d'envoyer deux fois la même alerte."""
    t = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "?"
    e = str(anime.get("episode") or "?")
    return f"{t}|{e}|{tag}"

def _should_alert(anime: Dict[str, Any], minutes_before: int) -> bool:
    """Détermine si on doit envoyer l'alerte en fonction du temps restant."""
    airing = anime.get("airingAt")
    if not airing:
        return False
    diff = airing - _now_ts()
    target = minutes_before * 60
    return 0 <= (target - diff) <= 60  # fenêtre de tolérance 60 sec

# ---------- Cog principal ----------

class Alerts(commands.Cog):
    """Alertes épisodes AniList (15/30 min avant)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sent = _load_sent()
        self.check_airing.start()

    def cog_unload(self) -> None:
        self.check_airing.cancel()
        _save_sent(self.sent)

    async def _get_alert_channel(self) -> Optional[discord.TextChannel]:
        """Récupère le salon défini par !setchannel depuis core.get_config()."""
        try:
            config = core.get_config()
            cid = config.get("channel_id")
            if not cid:
                LOG.warning("Aucun salon défini via !setchannel.")
                return None
            ch = self.bot.get_channel(int(cid))
            if ch is None:
                await self.bot.wait_until_ready()
                ch = self.bot.get_channel(int(cid))
            return ch if isinstance(ch, discord.TextChannel) else None
        except Exception as e:
            LOG.exception("Erreur récupération salon notifications: %s", e)
            return None

    async def _my_next(self) -> Optional[Dict[str, Any]]:
        """Récupère le prochain épisode de la liste globale."""
        try:
            return core.get_my_next_airing_one()
        except Exception as e:
            LOG.exception("get_my_next_airing_one failed: %s", e)
            return None

    async def _users_next(self) -> List[Dict[str, Any]]:
        """Récupère le prochain épisode pour chaque utilisateur lié."""
        out: List[Dict[str, Any]] = []
        try:
            links = core.load_links()
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
        """Envoie une alerte si elle n'a pas déjà été envoyée."""
        k = _key(anime, tag)
        if self.sent.get(k):
            return
        msg = f"⏰ **Alerte {tag} min**\n{_fmt(anime)}"
        try:
            await ch.send(msg)
            self.sent[k] = {"at": _now_ts()}
            _save_sent(self.sent)
            LOG.info("Alerte envoyée: %s", k)
        except Exception as e:
            LOG.exception("Envoi alerte échoué: %s", e)

    @tasks.loop(seconds=120)
    async def check_airing(self):
        """Vérifie toutes les 2 min les épisodes à venir."""
        ch = await self._get_alert_channel()
        if not ch:
            return

        # 1) Épisode global (ANILIST_USERNAME)
        mine = await self._my_next()
        if mine:
            for m in (30, 15):
                if _should_alert(mine, m):
                    await self._maybe_send(ch, mine, str(m))

        # 2) Épisodes des utilisateurs liés
        users = await self._users_next()
        for item in users:
            for m in (30, 15):
                if _should_alert(item, m):
                    await self._maybe_send(ch, item, str(m))

    @check_airing.before_loop
    async def before(self):
        await self.bot.wait_until_ready()
        LOG.info("Alerte épisodes: boucle démarrée.")

# ---------- Setup ----------

async def setup(bot):
    await bot.add_cog(Alerts(bot))
