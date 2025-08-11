"""
Daily digest (récap quotidien) envoyé en MP aux utilisateurs qui l'ont activé
via !reminder on, à l'heure définie par !setalert HH:MM.

- Lit les prefs dans core.load_user_settings() et core.load_preferences()
- Utilise AniList lié (core.load_links()) sinon fallback ANILIST_USERNAME
- Anti-doublon quotidien par user (data/daily_sent.json)
"""

from __future__ import annotations

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

from modules import core

LOG = logging.getLogger(__name__)

SENT_PATH = "data/daily_sent.json"  # {user_id: "YYYY-MM-DD"} dernière date envoyée

# ---------- persistance ----------
def _load_sent() -> Dict[str, str]:
    try:
        with open(SENT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_sent(data: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(SENT_PATH), exist_ok=True)
    with open(SENT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- util ----------
def _today_str_tz() -> str:
    # date du jour en Europe/Paris
    now_tz = datetime.now(tz=core.TIMEZONE)
    return now_tz.strftime("%Y-%m-%d")

def _is_today_ts(ts: int) -> bool:
    dt = datetime.fromtimestamp(ts, tz=core.TIMEZONE)
    today = datetime.now(tz=core.TIMEZONE).date()
    return dt.date() == today

def _format_time(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=core.TIMEZONE)
    return dt.strftime("%H:%M")

class DailyDigest(commands.Cog):
    """Envoi d'un récap quotidien en MP aux utilisateurs inscrits."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sent = _load_sent()
        self.loop_daily.start()

    def cog_unload(self):
        self.loop_daily.cancel()
        _save_sent(self.sent)

    # ---------- cœur : boucle minute ----------
    @tasks.loop(seconds=60)
    async def loop_daily(self):
        try:
            user_settings = core.load_user_settings() or {}   # {uid: {"reminder": bool}}
            prefs = core.load_preferences() or {}            # {uid: {"alert_time": "HH:MM"}}
            links = core.load_links() or {}                  # {uid: anilist_username}
        except Exception as e:
            LOG.exception("Lecture prefs/settings/links échouée: %s", e)
            return

        now_tz = datetime.now(tz=core.TIMEZONE)
        current_hhmm = now_tz.strftime("%H:%M")
        today_str = now_tz.strftime("%Y-%m-%d")

        # On parcourt tous les utilisateurs ayant des prefs
        uids: List[str] = sorted(set(user_settings.keys()) | set(prefs.keys()))
        if not uids:
            return

        for uid in uids:
            try:
                st = user_settings.get(uid, {})
                if st.get("reminder", True) is False:
                    continue  # user a désactivé

                alert_time = (prefs.get(uid, {}) or {}).get("alert_time")
                if not alert_time:
                    continue  # pas d'heure définie pour ce user

                # On déclenche uniquement quand l'heure correspond exactement (loop/minute)
                if alert_time != current_hhmm:
                    continue

                # déjà envoyé aujourd'hui ?
                if self.sent.get(uid) == today_str:
                    continue

                # Source des épisodes : AniList lié sinon global
                username = links.get(uid) or core.ANILIST_USERNAME
                if not username:
                    # Rien à envoyer si on ne sait pas quoi afficher
                    continue

                # Récupère tous les prochains et filtre ceux du jour
                episodes = core.get_upcoming_episodes(username) or []
                today_eps = [ep for ep in episodes if _is_today_ts(ep.get("airingAt", 0))]
                if not today_eps:
                    # Envoyer quand même un MP "rien aujourd'hui" ? On peut, c'est utile.
                    user = self.bot.get_user(int(uid)) or await self.bot.fetch_user(int(uid))
                    if user:
                        try:
                            await user.send("📭 **Récap du jour** : Rien de prévu aujourd'hui.")
                            self.sent[uid] = today_str
                            _save_sent(self.sent)
                        except discord.Forbidden:
                            LOG.warning("MP refusé par %s", uid)
                    continue

                # Trie par heure
                today_eps.sort(key=lambda e: e.get("airingAt", 0))

                # Construire l'embed
                embed = discord.Embed(
                    title="🗓️ Récap des sorties d'aujourd'hui",
                    description=f"Fuseau : {now_tz.tzname()}",
                    color=discord.Color.blurple()
                )
                # on limite raisonnablement la taille pour éviter un embed trop long
                for ep in today_eps[:25]:
                    title = ep.get("title") or ep.get("title_romaji") or ep.get("title_english") or "Titre inconnu"
                    if isinstance(title, dict):
                        # cas où c'est un dict AniList {romaji, english, native}
                        title = title.get("romaji") or title.get("english") or title.get("native") or "Titre inconnu"
                    epnum = ep.get("episode", "?")
                    hour  = _format_time(ep.get("airingAt", 0))
                    emoji = core.genre_emoji(ep.get("genres", []))
                    embed.add_field(
                        name=f"{emoji} {title} — Épisode {epnum}",
                        value=f"⏰ {hour}",
                        inline=False
                    )

                # Envoi en MP
                user = self.bot.get_user(int(uid)) or await self.bot.fetch_user(int(uid))
                if user:
                    try:
                        await user.send(embed=embed)
                        self.sent[uid] = today_str
                        _save_sent(self.sent)
                    except discord.Forbidden:
                        LOG.warning("MP refusé par %s", uid)

            except Exception as e:
                LOG.exception("Digest pour %s échoué: %s", uid, e)

    @loop_daily.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    # ---------- commande de test owner ----------
    @commands.command(name="testdigest")
    @commands.is_owner()
    async def test_digest(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Envoie immédiatement un digest du jour à toi (ou au user donné)."""
        target = user or ctx.author
        links = core.load_links() or {}
        username = links.get(str(target.id)) or core.ANILIST_USERNAME
        if not username:
            return await ctx.send("Aucun AniList configuré (link manquant et ANILIST_USERNAME vide).")

        episodes = core.get_upcoming_episodes(username) or []
        today_eps = [ep for ep in episodes if _is_today_ts(ep.get("airingAt", 0))]

        embed = discord.Embed(
            title="🗓️ Récap des sorties d'aujourd'hui (TEST)",
            color=discord.Color.green()
        )
        if today_eps:
            today_eps.sort(key=lambda e: e.get("airingAt", 0))
            for ep in today_eps[:25]:
                title = ep.get("title") or ep.get("title_romaji") or ep.get("title_english") or "Titre inconnu"
                if isinstance(title, dict):
                    title = title.get("romaji") or title.get("english") or title.get("native") or "Titre inconnu"
                epnum = ep.get("episode", "?")
                hour  = _format_time(ep.get("airingAt", 0))
                emoji = core.genre_emoji(ep.get("genres", []))
                embed.add_field(name=f"{emoji} {title} — Épisode {epnum}", value=f"⏰ {hour}", inline=False)
        else:
            embed.description = "📭 Rien de prévu aujourd'hui."

        try:
            await target.send(embed=embed)
            await ctx.send(f"✅ Digest envoyé en MP à **{target.display_name}**.")
        except discord.Forbidden:
            await ctx.send("❌ Impossible d'envoyer un MP à cet utilisateur (DM fermés).")


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyDigest(bot))
