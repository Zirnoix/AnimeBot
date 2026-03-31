# cogs/openings.py
from __future__ import annotations
import logging
import os
import random
import asyncio
import re
import tempfile
from dataclasses import dataclass
from typing import List
import json
import subprocess
import time

import aiohttp
import discord
from discord.ext import commands, tasks

from modules import anilist_gate
from modules import core
from modules import voice              # ensure_connected + make_source précis/robuste
from modules import animethemes        # provider AnimeThemes + filtres AniList
from modules import guessop_catalog as gopc

LOG = logging.getLogger(__name__)

# Cooldown après la fin d’une partie Guess OP (lanceur uniquement)
GUESSOP_COOLDOWN_AFTER_SEC = 15.0
_last_guessop_end_by_user: dict[int, float] = {}


def _guessop_cooldown_remaining(uid: int) -> float:
    t = _last_guessop_end_by_user.get(uid)
    if t is None:
        return 0.0
    return max(0.0, GUESSOP_COOLDOWN_AFTER_SEC - (time.monotonic() - t))


def _mark_guessop_end(uid: int) -> None:
    _last_guessop_end_by_user[uid] = time.monotonic()


# ==== Configuration ====
USE_ANIMETHEMES = True          # Active l’utilisation d’AnimeThemes.moe
DURATION_SEC = 20               # Durée de l’extrait audio
ANSWER_TIMEOUT = 30             # Temps pour répondre (secondes)
COUNTDOWN_STEP = 5              # Fréquence d’update de l’embed (s)
FADE_SEC = 1.0                  # Durée du fade-in/out

# → Pour stabiliser pendant le debug : False. Tu pourras le remettre à True après.
ENABLE_RANDOM_SEEK = False       # Démarrer au milieu pour éviter l’intro trop facile
RANDOM_SEEK_MAX = 45.0           # Seek aléatoire max (s) si la vidéo est assez longue

# Marges anti-lag
START_GUARD_TIMEOUT = 3.0        # max 3s pour détecter le démarrage
PLAY_TIMEOUT_MARGIN = 3.0        # +3s de marge à l’attente de fin

NORMALIZE_AUDIO = False          # Normalisation loudness (peut coûter un peu de CPU)

# Filtres AniList (si on pioche via AnimeThemes) + cache
ANILIST_CACHE_TTL = 60 * 60 * 12  # 12h
_ANILIST_CACHE: dict[str, tuple[float, list[str]]] = {}

MIN_YEAR = 2005
MIN_SCORE_10 = 5.0
BANNED_GENRES = {"mahou shoujo", "kids"}
BANNED_FORMATS = {"MUSIC"}

# Fichiers locaux de secours
LOCAL_AUDIO_FOLDER = "assets/audio/openings"
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")

# Catalogue SQLite : priorité quand assez d’entrées (0–1, plus = plus de catalogue)
CATALOG_PICK_BIAS = float(os.getenv("GUESSOP_CATALOG_BIAS", "0.88"))
CATALOG_MIN_FOR_BIAS = int(os.getenv("GUESSOP_CATALOG_MIN", "5"))

# Guess OP chaîne : plafond de sécurité (manches avec au moins un gagnant)
MAX_GUESSOP_CHAIN_ROUNDS = int(os.getenv("GUESSOP_CHAIN_MAX_ROUNDS", "25"))

# Pause (secondes) après le scoreboard d’une manche avant la suivante (ou avant le récap final).
def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float((os.getenv(name) or str(default)).strip())
    except ValueError:
        v = default
    return max(lo, min(hi, v))


GUESSOP_CHAIN_PAUSE_BETWEEN_SEC = _env_float("GUESSOP_CHAIN_PAUSE_BETWEEN_SEC", 12.0, 5.0, 45.0)

# XP bonus par palier de série (manche 2 d’affilée = 1 palier, etc.)
GUESSOP_CHAIN_STREAK_XP_PER = int(os.getenv("GUESSOP_CHAIN_STREAK_XP", "5"))

# AnimeThemes + filtre AniList : tentatives max (chaque tentative = API + GraphQL si besoin)
GUESSOP_FILTER_MAX_ATTEMPTS = int(os.getenv("GUESSOP_FILTER_MAX_ATTEMPTS", "10"))

# ================== UTILS ==================
def _get_cached_titles(key: str) -> list[str] | None:
    item = _ANILIST_CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if (time.time() - ts) > ANILIST_CACHE_TTL:
        return None
    return data

def _set_cached_titles(key: str, titles: list[str]) -> None:
    _ANILIST_CACHE[key] = (time.time(), titles)

def _probe_duration_sec(path: str) -> float | None:
    """Retourne la durée en secondes via ffprobe, ou None si indispo."""
    try:
        out = subprocess.check_output(
            [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            stderr=subprocess.STDOUT,
        )
        data = json.loads(out.decode("utf-8", "ignore"))
        dur = float(data.get("format", {}).get("duration", 0.0))
        if dur > 0:
            return dur
    except Exception:
        return None
    return None

def _safe_seek(duration: float | None, want_duration: float, max_seek: float) -> float:
    """
    Calcule un seek aléatoire qui garantit au moins want_duration secondes restantes (+1s marge).
    Si on ne connaît pas la durée, borne simplement à max_seek.
    """
    if duration is None or duration <= 0:
        return round(random.uniform(0.0, max_seek), 2)
    max_start = max(0.0, duration - (want_duration + 1.0))  # 1s de marge
    if max_start <= 0:
        return 0.0
    return round(random.uniform(0.0, min(max_start, max_seek)), 2)

def _clean_title_from_filename(name: str) -> str:
    """Nettoie un nom de fichier en titre lisible."""
    base = os.path.splitext(name)[0]
    base = re.sub(r"[\[\(].*?[\]\)]", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\b(OP|OPENING|ED|ENDING)\s*\d*\b", "", base, flags=re.IGNORECASE)
    base = re.sub(r"[_\-]+", " ", base)
    base = re.sub(r"\s{2,}", " ", base).strip()
    return base or os.path.splitext(name)[0]

async def _fetch_to_temp(url: str, timeout_total: float = 45.0, retries: int = 2) -> str:
    """Télécharge l'URL avec petits retries/backoff. Renvoie un chemin local."""
    ext = os.path.splitext(url)[1] or ".dat"
    fd, tmp_path = tempfile.mkstemp(suffix=ext); os.close(fd)

    backoff = 0.6
    last_err = None
    for _ in range(retries + 1):
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": "AnimeBot/guessop"}) as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=timeout_total)) as r:
                    r.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        async for chunk in r.content.iter_chunked(65536):
                            if chunk:
                                f.write(chunk)
            return tmp_path
        except Exception as e:
            last_err = e
            await asyncio.sleep(backoff)
            backoff *= 1.7

    # échec total
    try: os.remove(tmp_path)
    except Exception: pass
    raise last_err

def _bar(remaining: int, total: int, width: int = 10) -> str:
    filled = int(width * (total - remaining) / max(1, total))
    return "█" * filled + "░" * (width - filled)

def _build_question_embed(
    choices: List[str],
    remaining_sec: int,
    footer: str | None = None,
    responders: List[str] | None = None,
    title: str = "🎵 Devine l’opening !",
) -> discord.Embed:
    """`responders` est ignoré (plus d’affichage des noms dans le salon pour limiter le spam)."""
    em = discord.Embed(
        title=title,
        description=(
            f"{_bar(remaining_sec, ANSWER_TIMEOUT)}  **{remaining_sec}s** restantes.\n"
            "Clique sur **1–4** pour répondre *(même salon vocal que le bot)*."
        ),
        color=discord.Color.purple()
    )
    for i, title in enumerate(choices, 1):
        em.add_field(name=f"{i}️⃣", value=title, inline=False)
    if footer:
        em.set_footer(text=footer)
    return em

# ================== UI (BOUTONS) ==================
class GuessOPView(discord.ui.View):
    def __init__(
        self,
        bot,
        ctx,
        voice_channel,
        choices,
        correct_index,
        timeout_sec=ANSWER_TIMEOUT,
        source_footer: str = "",
        question_title: str | None = None,
    ):
        super().__init__(timeout=timeout_sec)
        self.bot = bot
        self.ctx = ctx
        self.voice_channel = voice_channel
        self.choices = choices
        self.correct_index = correct_index
        self.source_footer = source_footer
        self._question_title = question_title or "🎵 Devine l’opening !"
        self.already_answered: set[int] = set()
        self._remaining = timeout_sec
        self._embed_lock = asyncio.Lock()
        self.winners_order: list[discord.Member] = []
        self.others_correct: list[discord.Member] = []
        self._lock = asyncio.Lock()
        self.message: discord.Message | None = None

        for i in range(4):
            self.add_item(GuessOPButton(i))

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

class GuessOPButton(discord.ui.Button):
    def __init__(self, index: int):
        super().__init__(label=str(index + 1), style=discord.ButtonStyle.primary)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: GuessOPView = self.view  # type: ignore
        if interaction.user.bot:
            return await interaction.response.defer(ephemeral=True)

        # Vérifier si joueur est bien dans le vocal
        if not interaction.user.voice or interaction.user.voice.channel != view.voice_channel:
            return await interaction.response.send_message(
                "🔇 Tu dois être dans **le même salon vocal** pour répondre.",
                ephemeral=True
            )

        async with view._lock:
            if interaction.user.id in view.already_answered:
                return await interaction.response.send_message("✋ Une seule réponse par joueur.", ephemeral=True)
            view.already_answered.add(interaction.user.id)

            if self.index == view.correct_index:
                if len(view.winners_order) < 3:
                    view.winners_order.append(interaction.user)
                    await interaction.response.send_message("✅ Bonne réponse !", ephemeral=True)
                else:
                    view.others_correct.append(interaction.user)
                    await interaction.response.send_message("✅ Bonne réponse (hors podium) !", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Mauvaise réponse.", ephemeral=True)


@dataclass
class GuessOPRoundOutcome:
    correct_anime: str
    theme_label: str | None
    source_footer: str
    view: GuessOPView
    vc: discord.VoiceClient


def _guessop_schedule_question_delete(msg: discord.Message | None, delay: float = 30.0) -> None:
    if not msg:
        return

    async def _go() -> None:
        try:
            await asyncio.sleep(delay)
            await msg.delete()
        except Exception:
            pass

    asyncio.create_task(_go())


async def _safe_delete_message(msg: discord.Message | None) -> None:
    if not msg:
        return
    try:
        await msg.delete()
    except Exception:
        pass


async def _guessop_send_cooldown_notice(ctx: commands.Context, left_go: float) -> None:
    """Message vu uniquement par l’auteur : slash = éphémère ; préfixe = MP ou message effacé."""
    msg = (
        f"⏳ Attends **{int(left_go) + 1}s** après la fin du dernier Guess OP avant de relancer."
    )
    itx = getattr(ctx, "interaction", None)
    if itx:
        try:
            await itx.followup.send(msg, ephemeral=True)
        except Exception:
            pass
        return
    try:
        await ctx.author.send(msg)
    except Exception:
        try:
            await ctx.reply(msg, mention_author=False, delete_after=15)
        except Exception:
            pass


# ================== COG ==================
class Openings(commands.Cog):
    """Mini-jeu GuessOP (openings d’anime, boutons, multi-joueurs, audio)."""

    def __init__(self, bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}  # anti-double partie par serveur
        try:
            gopc.init_db()
            imported = gopc.import_legacy_json()
            if imported:
                LOG.info("Guess OP catalogue : +%d entrées (import legacy JSON)", imported)
        except Exception as e:
            LOG.warning("guessop_catalog init: %s", e)
        try:
            self.guessop_catalog_harvest.start()
        except Exception:
            pass

    def cog_unload(self) -> None:
        try:
            self.guessop_catalog_harvest.cancel()
        except Exception:
            pass

    def _guild_lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    @tasks.loop(hours=8)
    async def guessop_catalog_harvest(self) -> None:
        """Enrichit le catalogue : une page listée + tirages aléatoires (URLs souvent déjà vues si base énorme)."""
        if not USE_ANIMETHEMES:
            return
        before = gopc.count()
        new_inserts = 0
        try:
            max_page = await animethemes.anime_catalog_max_page(40)
            page = random.randint(1, max_page) if max_page > 0 else 1
            items = await animethemes.harvest_openings_from_page(page, 40)
            for t, th, url in items:
                if url.startswith(("http://", "https://")):
                    _, ins = gopc.add_opening(t, th, url, "harvest_auto_page")
                    if ins:
                        new_inserts += 1
        except Exception as e:
            LOG.debug("guessop page harvest: %s", e)
        await asyncio.sleep(1.0)
        for _ in range(24):
            try:
                got = await animethemes.random_opening()
                if got:
                    t, th, url = got
                    if url.startswith(("http://", "https://")):
                        _, ins = gopc.add_opening(t, th, url, "harvest_auto_random")
                        if ins:
                            new_inserts += 1
            except Exception:
                pass
            await asyncio.sleep(2.0)
        after = gopc.count()
        if new_inserts:
            LOG.info(
                "Guess OP harvest auto : %d → %d entrées, +%d nouvelles URLs",
                before,
                after,
                new_inserts,
            )

    @guessop_catalog_harvest.before_loop
    async def _before_guessop_harvest(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(180)

    async def _guessop_award_and_embed(
        self,
        ctx: commands.Context,
        send,
        outcome: GuessOPRoundOutcome,
        *,
        round_manche: int | None = None,
    ) -> None:
        view = outcome.view
        correct_anime = outcome.correct_anime
        theme_label = outcome.theme_label
        source_footer = outcome.source_footer
        podium_xp = [15, 10, 7]
        others_xp = 3
        award_lines = []
        for rank, user in enumerate(view.winners_order, start=1):
            xp = podium_xp[rank - 1]
            award_lines.append(f"**#{rank}** {user.mention} — +{xp} XP")
            try:
                await core.add_xp(self.bot, ctx.channel, user.id, xp)
            except Exception:
                pass
            try:
                core.add_mini_score(user.id, "guessop", 1)
            except Exception:
                pass
        for user in view.others_correct:
            award_lines.append(f"• {user.mention} — +{others_xp} XP")
            try:
                await core.add_xp(self.bot, ctx.channel, user.id, others_xp)
            except Exception:
                pass
            try:
                core.add_mini_score(user.id, "guessop", 1)
            except Exception:
                pass
        fast_line = f"⚡ Plus rapide : {view.winners_order[0].mention}" if view.winners_order else None
        title_res = (
            f"🏁 Résultats — Guess OP · Manche {round_manche}"
            if round_manche
            else "🏁 Résultats — Guess OP"
        )
        res = discord.Embed(
            title=title_res,
            description=f"✅ **Réponse :** {correct_anime}",
            color=discord.Color.gold(),
        )
        if theme_label:
            res.add_field(name="Opening", value=theme_label, inline=False)
        if fast_line:
            res.add_field(name="Vitesse", value=fast_line, inline=False)
        if award_lines:
            res.add_field(name="Récompenses", value="\n".join(award_lines), inline=False)
        if source_footer:
            res.set_footer(text=source_footer)
        await send(embed=res)
        _guessop_schedule_question_delete(view.message)

    async def _guessop_chain_award_round(
        self,
        ctx: commands.Context,
        send,
        outcome: GuessOPRoundOutcome,
        round_manche: int,
        chain_streaks: dict[int, int],
        max_streak_ever: dict[int, int],
        totals_xp: dict[int, int],
        wins: dict[int, int],
    ) -> discord.Message | None:
        """Récompenses manche chaîne + bonus de série ; met à jour totaux / séries."""
        view = outcome.view
        correct_anime = outcome.correct_anime
        theme_label = outcome.theme_label
        source_footer = outcome.source_footer
        podium_xp = [15, 10, 7]
        others_xp = 3

        correct_ids: set[int] = set()
        for u in view.winners_order:
            correct_ids.add(u.id)
        for u in view.others_correct:
            correct_ids.add(u.id)

        tracked = set(chain_streaks.keys()) | correct_ids
        for uid in tracked:
            if uid in correct_ids:
                ns = chain_streaks.get(uid, 0) + 1
                chain_streaks[uid] = ns
                max_streak_ever[uid] = max(max_streak_ever.get(uid, 0), ns)
            else:
                chain_streaks[uid] = 0

        award_lines: list[str] = []
        streak_lines: list[str] = []

        for rank, user in enumerate(view.winners_order, start=1):
            base = podium_xp[rank - 1]
            uid = user.id
            st = chain_streaks.get(uid, 0)
            extra = max(0, st - 1) * GUESSOP_CHAIN_STREAK_XP_PER if st >= 2 else 0
            total_u = base + extra
            totals_xp[uid] = totals_xp.get(uid, 0) + total_u
            wins[uid] = wins.get(uid, 0) + 1
            line = f"**#{rank}** {user.mention} — +{base} XP"
            if extra > 0:
                line += f" · **+{extra} XP** série (×{st})"
                streak_lines.append(f"{user.mention} — série **{st}** → +{extra} XP")
            try:
                await core.add_xp(self.bot, ctx.channel, user.id, total_u)
            except Exception:
                pass
            try:
                core.add_mini_score(user.id, "guessop", 1)
            except Exception:
                pass
            award_lines.append(line)

        for user in view.others_correct:
            uid = user.id
            base = others_xp
            st = chain_streaks.get(uid, 0)
            extra = max(0, st - 1) * GUESSOP_CHAIN_STREAK_XP_PER if st >= 2 else 0
            total_u = base + extra
            totals_xp[uid] = totals_xp.get(uid, 0) + total_u
            wins[uid] = wins.get(uid, 0) + 1
            line = f"• {user.mention} — +{base} XP"
            if extra > 0:
                line += f" · **+{extra} XP** série (×{st})"
                streak_lines.append(f"{user.mention} — série **{st}** → +{extra} XP")
            try:
                await core.add_xp(self.bot, ctx.channel, user.id, total_u)
            except Exception:
                pass
            try:
                core.add_mini_score(user.id, "guessop", 1)
            except Exception:
                pass
            award_lines.append(line)

        fast_line = f"⚡ Plus rapide : {view.winners_order[0].mention}" if view.winners_order else None
        title_res = f"🏁 Résultats — Guess OP · Manche {round_manche}"
        res = discord.Embed(
            title=title_res,
            description=f"✅ **Réponse :** {correct_anime}",
            color=discord.Color.gold(),
        )
        if theme_label:
            res.add_field(name="Opening", value=theme_label, inline=False)
        if fast_line:
            res.add_field(name="Vitesse", value=fast_line, inline=False)
        if award_lines:
            res.add_field(name="Récompenses", value="\n".join(award_lines), inline=False)
        if streak_lines:
            res.add_field(name="Bonus série", value="\n".join(streak_lines), inline=False)
        if source_footer:
            res.set_footer(text=source_footer)
        sent = await send(embed=res)
        return sent if isinstance(sent, discord.Message) else None

    def _guessop_chain_recap_embed(
        self,
        ctx: commands.Context,
        totals_xp: dict[int, int],
        wins: dict[int, int],
        max_streak_ever: dict[int, int],
        *,
        title: str,
        description: str | None,
    ) -> discord.Embed:
        emb = discord.Embed(title=title, description=description, color=discord.Color.dark_gold())
        if not totals_xp:
            emb.add_field(name="Totaux", value="Aucun point marqué sur la chaîne.", inline=False)
            return emb
        guild = ctx.guild
        rows: list[tuple[int, int, int, int]] = []
        for uid, tx in totals_xp.items():
            rows.append((uid, tx, wins.get(uid, 0), max_streak_ever.get(uid, 0)))
        rows.sort(key=lambda x: -x[1])
        lines: list[str] = []
        for uid, tx, wn, ms in rows[:20]:
            mem = guild.get_member(uid) if guild else None
            mention = mem.mention if mem else f"<@{uid}>"
            lines.append(f"{mention} — **{tx} XP** · {wn} victoire(s) · série max **{ms}**")
        if len(rows) > 20:
            lines.append(f"*… et {len(rows) - 20} autre(s)*")
        emb.add_field(name="Totaux sur la chaîne", value="\n".join(lines), inline=False)
        return emb

    async def _run_one_guessop_round(
        self,
        ctx: commands.Context,
        voice_channel: discord.VoiceChannel,
        send,
        *,
        linked_anilist: str | None,
        user_romaji_list: list[str],
        user_titles_lower: set[str],
        disconnect_after: bool,
        vc_existing: discord.VoiceClient | None,
        chain_round: int | None = None,
    ) -> GuessOPRoundOutcome | None:
        correct_anime = None
        theme_label = None
        media_source = None
        source_footer = ""

        n_cat = gopc.count()
        if linked_anilist and user_titles_lower and n_cat >= CATALOG_MIN_FOR_BIAS:
            picked_list = gopc.pick_random_title_in_set(user_titles_lower)
            if picked_list:
                oid, correct_anime, theme_label, media_source = picked_list
                source_footer = f"Catalogue Guess OP · depuis ta liste AniList · {n_cat} openings"
                gopc.record_used(oid)

        if not media_source and n_cat >= CATALOG_MIN_FOR_BIAS and random.random() < CATALOG_PICK_BIAS:
            picked = gopc.pick_random()
            if picked:
                oid, correct_anime, theme_label, media_source = picked
                source_footer = f"Catalogue Guess OP · {n_cat} openings"
                gopc.record_used(oid)

        if not media_source:
            got = None
            if USE_ANIMETHEMES:
                try:
                        got = await animethemes.random_opening_filtered(
                            min_year=MIN_YEAR,
                            min_score_10=MIN_SCORE_10,
                            banned_genres=BANNED_GENRES,
                            banned_formats=BANNED_FORMATS,
                            max_attempts=GUESSOP_FILTER_MAX_ATTEMPTS,
                        )
                except Exception:
                    got = None

                if got:
                    title, theme_label, video_url = got
                    correct_anime = title
                    media_source = video_url
                    source_footer = "Source : AnimeThemes.moe → ajout catalogue"
                    if video_url.startswith(("http://", "https://")):
                        _, _ = gopc.add_opening(
                            correct_anime, theme_label or "OP", video_url, "animethemes_live"
                        )

        if not media_source:
            if not os.path.exists(LOCAL_AUDIO_FOLDER):
                await send("❌ Aucun opening trouvé (AnimeThemes vide + pas de dossier local).")
                return None
            files = [f for f in os.listdir(LOCAL_AUDIO_FOLDER) if f.lower().endswith(".mp3")]
            if not files:
                await send("❌ Aucun opening trouvé dans le dossier local.")
                return None
            pick = random.choice(files)
            media_source = os.path.join(LOCAL_AUDIO_FOLDER, pick)
            correct_anime = _clean_title_from_filename(pick)
            source_footer = "Source : fichiers locaux"

        async def _prepare_local_file():
            local_path = media_source
            cleanup = False
            if isinstance(media_source, str) and media_source.startswith(("http://", "https://")):
                local_path = await _fetch_to_temp(media_source)
                cleanup = True
            return local_path, cleanup

        prepare_task = asyncio.create_task(_prepare_local_file())

        cache_key = "popular_romaji_60"
        pool = _get_cached_titles(cache_key)
        if pool is None:
            if core._anilist_slots_available() <= 0:
                try:
                    await send("⏳ **File AniList** — récupération des propositions…")
                except Exception:
                    pass
            query = '''
            query {
              Page(perPage: 60) {
                media(type: ANIME, sort: POPULARITY_DESC) {
                  title { romaji }
                }
              }
            }
            '''
            try:
                data = await core.query_anilist_async(query, queue_ctx=ctx)
                pool = [m["title"]["romaji"] for m in data["data"]["Page"]["media"]]
                _set_cached_titles(cache_key, pool)
            except Exception:
                pool = []

        choices = [correct_anime]
        if user_romaji_list:
            list_alts = [t for t in user_romaji_list if t.lower() != (correct_anime or "").lower()]
            random.shuffle(list_alts)
            for alt in list_alts:
                if len(choices) >= 4:
                    break
                alt_clean = _clean_title_from_filename(alt)
                if alt_clean and alt_clean.lower() != (correct_anime or "").lower() and alt_clean not in choices:
                    choices.append(alt_clean)
        # Leurres catalogue : même type de titres que l’opening jouée (évite 3× top AniList vs 1× « inconnu »).
        need_lr = 4 - len(choices)
        if need_lr > 0 and gopc.count() >= CATALOG_MIN_FOR_BIAS:
            excl = set(choices) | {correct_anime or ""}
            for raw in gopc.random_distractor_titles(exclude_titles=excl, max_titles=need_lr):
                if len(choices) >= 4:
                    break
                alt_clean = _clean_title_from_filename(raw)
                if (
                    alt_clean
                    and alt_clean.lower() != (correct_anime or "").lower()
                    and alt_clean not in choices
                ):
                    choices.append(alt_clean)

        tries = 0
        while len(choices) < 4 and pool and tries < 200:
            alt = _clean_title_from_filename(random.choice(pool))
            tries += 1
            if alt and alt.lower() != (correct_anime or "").lower() and alt not in choices:
                choices.append(alt)
        while len(choices) < 4:
            choices.append(f"Option {len(choices) + 1}")
        random.shuffle(choices)
        correct_index = choices.index(correct_anime)

        q_title = (
            f"🎵 Devine l'opening ! · Manche {chain_round}"
            if chain_round is not None
            else "🎵 Devine l'opening !"
        )
        em = _build_question_embed(choices, ANSWER_TIMEOUT, source_footer, [], title=q_title)
        view = GuessOPView(
            self.bot,
            ctx,
            voice_channel,
            choices,
            correct_index,
            timeout_sec=ANSWER_TIMEOUT,
            source_footer=source_footer,
            question_title=q_title,
        )
        sent = await send(embed=em, view=view)
        if isinstance(sent, discord.Message):
            view.message = sent

        vc: discord.VoiceClient | None = vc_existing
        if vc is None or not vc.is_connected():
            try:
                vc = await voice.ensure_connected(voice_channel)
            except Exception as e:
                _mark_guessop_end(ctx.author.id)
                await send(f"❌ Impossible de rejoindre le vocal : {e}")
                await _safe_delete_message(view.message)
                return None

        async def _tick_embed():
            await asyncio.sleep(1.5)
            remaining = ANSWER_TIMEOUT
            while remaining > 0 and not view.is_finished() and view.message:
                await asyncio.sleep(COUNTDOWN_STEP)
                remaining = max(0, remaining - COUNTDOWN_STEP)
                view._remaining = remaining
                try:
                    async with view._embed_lock:
                        await view.message.edit(
                            embed=_build_question_embed(
                                choices, remaining, source_footer, None, title=view._question_title
                            ),
                            view=view,
                        )
                except Exception:
                    break

        countdown_task = asyncio.create_task(_tick_embed())

        async def _end_round_after_timeout():
            await asyncio.sleep(ANSWER_TIMEOUT)
            try:
                for item in view.children:
                    if isinstance(item, discord.ui.Button):
                        item.disabled = True
                if view.message:
                    await view.message.edit(view=view)
            except Exception:
                pass
            view.stop()

        end_timer_task = asyncio.create_task(_end_round_after_timeout())

        local_path = None
        cleanup = False

        try:
            local_path, cleanup = await prepare_task
            if not vc.is_connected():
                vc = await voice.ensure_connected(voice_channel)

            if vc.is_playing():
                try:
                    vc.stop()
                except Exception:
                    pass

            media_duration = _probe_duration_sec(local_path)
            seek_start = _safe_seek(media_duration, DURATION_SEC, RANDOM_SEEK_MAX) if ENABLE_RANDOM_SEEK else 0.0

            source = voice.make_source(
                local_path,
                duration_sec=float(DURATION_SEC),
                seek_start=float(seek_start),
                fade_sec=float(FADE_SEC),
                normalize=bool(NORMALIZE_AUDIO),
            )

            done_event = asyncio.Event()

            def _after_play(err: Exception | None):
                try:
                    done_event.set()
                except Exception:
                    pass

            vc.play(source, after=_after_play)

            started = False
            for _ in range(int(START_GUARD_TIMEOUT / 0.1)):
                await asyncio.sleep(0.1)
                if vc.is_playing():
                    started = True
                    break

            if not started and ENABLE_RANDOM_SEEK and seek_start > 0.0:
                try:
                    vc.stop()
                except Exception:
                    pass
                source2 = voice.make_source(
                    local_path,
                    duration_sec=float(DURATION_SEC),
                    seek_start=0.0,
                    fade_sec=float(FADE_SEC),
                    normalize=bool(NORMALIZE_AUDIO),
                )
                done_event = asyncio.Event()

                def _after_play2(err: Exception | None):
                    try:
                        done_event.set()
                    except Exception:
                        pass

                vc.play(source2, after=_after_play2)

                for _ in range(int(START_GUARD_TIMEOUT / 0.1)):
                    await asyncio.sleep(0.1)
                    if vc.is_playing():
                        started = True
                        break

            try:
                await asyncio.wait_for(done_event.wait(), timeout=float(DURATION_SEC) + PLAY_TIMEOUT_MARGIN)
            except asyncio.TimeoutError:
                try:
                    vc.stop()
                except Exception:
                    pass

        except Exception as e:
            try:
                await send(f"⚠️ Audio non lancé : {e}")
            except Exception:
                pass
        finally:
            if cleanup and local_path:
                try:
                    os.remove(local_path)
                except Exception:
                    pass

        try:
            await view.wait()
        except Exception:
            pass

        if not end_timer_task.done():
            end_timer_task.cancel()
        if not countdown_task.done():
            countdown_task.cancel()

        if disconnect_after:
            try:
                if vc and vc.is_connected():
                    await vc.disconnect(force=False)
            except Exception:
                pass

        assert correct_anime is not None
        return GuessOPRoundOutcome(
            correct_anime=correct_anime,
            theme_label=theme_label,
            source_footer=source_footer,
            view=view,
            vc=vc,
        )

    @commands.hybrid_command(
        name="guessop",
        description="Devine l'opening (20s audio + 4 choix ; AniList lié → priorité + leurres depuis ta liste).",
    )
    async def guess_op(self, ctx: commands.Context) -> None:
        if getattr(ctx, "interaction", None):
            try:
                await ctx.interaction.response.defer()
            except Exception:
                pass

        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return

        send = (ctx.interaction.followup.send if getattr(ctx, "interaction", None) else ctx.send)

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await send("🔇 Tu dois être dans un **salon vocal** pour jouer.")
        voice_channel: discord.VoiceChannel = ctx.author.voice.channel

        left_go = _guessop_cooldown_remaining(ctx.author.id)
        if left_go > 0:
            await _guessop_send_cooldown_notice(ctx, left_go)
            return

        linked_anilist = core.get_linked_username(ctx.author.id)
        user_romaji_list: list[str] = []
        user_titles_lower: set[str] = set()
        if linked_anilist:
            ml = core.fetch_user_list_media_for_minigames(linked_anilist)
            for m in ml:
                r = ((m.get("title") or {}).get("romaji") or "").strip()
                if r:
                    user_romaji_list.append(r)
                    user_titles_lower.add(r.lower())

        async with self._guild_lock(ctx.guild.id):
            outcome = await self._run_one_guessop_round(
                ctx,
                voice_channel,
                send,
                linked_anilist=linked_anilist,
                user_romaji_list=user_romaji_list,
                user_titles_lower=user_titles_lower,
                disconnect_after=True,
                vc_existing=None,
                chain_round=None,
            )
            if outcome is None:
                return

            if not outcome.view.winners_order and not outcome.view.others_correct:
                _mark_guessop_end(ctx.author.id)
                return await send(
                    f"⏰ Temps écoulé ! La bonne réponse était : **{outcome.correct_anime}**"
                )

            await self._guessop_award_and_embed(ctx, send, outcome, round_manche=None)
            _mark_guessop_end(ctx.author.id)

    @commands.hybrid_command(
        name="guessopchain",
        # Max 100 caractères (exigence API Discord slash).
        description=(
            "Guess OP en chaîne : reste en vocal, nouvelle manche après le timer. Arrêt si échec."
        ),
    )
    async def guess_op_chain(self, ctx: commands.Context) -> None:
        if getattr(ctx, "interaction", None):
            try:
                await ctx.interaction.response.defer()
            except Exception:
                pass

        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return

        send = (ctx.interaction.followup.send if getattr(ctx, "interaction", None) else ctx.send)

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await send("🔇 Tu dois être dans un **salon vocal** pour jouer.")
        voice_channel: discord.VoiceChannel = ctx.author.voice.channel

        left_go = _guessop_cooldown_remaining(ctx.author.id)
        if left_go > 0:
            await _guessop_send_cooldown_notice(ctx, left_go)
            return

        linked_anilist = core.get_linked_username(ctx.author.id)
        user_romaji_list: list[str] = []
        user_titles_lower: set[str] = set()
        if linked_anilist:
            ml = core.fetch_user_list_media_for_minigames(linked_anilist)
            for m in ml:
                r = ((m.get("title") or {}).get("romaji") or "").strip()
                if r:
                    user_romaji_list.append(r)
                    user_titles_lower.add(r.lower())

        async with self._guild_lock(ctx.guild.id):
            vc: discord.VoiceClient | None = None
            round_num = 0
            last_result_msg: discord.Message | None = None
            chain_streaks: dict[int, int] = {}
            max_streak_ever: dict[int, int] = {}
            totals_xp: dict[int, int] = {}
            wins: dict[int, int] = {}

            while round_num < MAX_GUESSOP_CHAIN_ROUNDS:
                round_num += 1

                await _safe_delete_message(last_result_msg)
                last_result_msg = None

                outcome = await self._run_one_guessop_round(
                    ctx,
                    voice_channel,
                    send,
                    linked_anilist=linked_anilist,
                    user_romaji_list=user_romaji_list,
                    user_titles_lower=user_titles_lower,
                    disconnect_after=False,
                    vc_existing=vc,
                    chain_round=round_num,
                )
                if outcome is None:
                    if vc and vc.is_connected():
                        try:
                            await vc.disconnect(force=False)
                        except Exception:
                            pass
                    _mark_guessop_end(ctx.author.id)
                    return

                vc = outcome.vc

                if not outcome.view.winners_order and not outcome.view.others_correct:
                    await _safe_delete_message(outcome.view.message)
                    try:
                        if vc and vc.is_connected():
                            await vc.disconnect(force=False)
                    except Exception:
                        pass
                    _mark_guessop_end(ctx.author.id)
                    recap = self._guessop_chain_recap_embed(
                        ctx,
                        totals_xp,
                        wins,
                        max_streak_ever,
                        title="📊 Guess OP chaîne — fin",
                        description=(
                            "⏰ **Personne n'a trouvé** cette manche.\n"
                            f"Réponse : **{outcome.correct_anime}**"
                        ),
                    )
                    return await send(embed=recap)

                await _safe_delete_message(outcome.view.message)
                last_result_msg = await self._guessop_chain_award_round(
                    ctx,
                    send,
                    outcome,
                    round_num,
                    chain_streaks,
                    max_streak_ever,
                    totals_xp,
                    wins,
                )
                if round_num < MAX_GUESSOP_CHAIN_ROUNDS:
                    await asyncio.sleep(GUESSOP_CHAIN_PAUSE_BETWEEN_SEC)

            try:
                if vc and vc.is_connected():
                    await vc.disconnect(force=False)
            except Exception:
                pass
            _mark_guessop_end(ctx.author.id)

            await asyncio.sleep(GUESSOP_CHAIN_PAUSE_BETWEEN_SEC)
            await _safe_delete_message(last_result_msg)
            recap = self._guessop_chain_recap_embed(
                ctx,
                totals_xp,
                wins,
                max_streak_ever,
                title="📊 Guess OP chaîne — fin",
                description=(
                    f"🔚 Limite de **{MAX_GUESSOP_CHAIN_ROUNDS}** manches atteintes — le bot a quitté le vocal."
                ),
            )
            await send(embed=recap)

    # --- DIAG AUDIO intégré au même Cog ---
    @commands.hybrid_command(name="voicediag", description="Diagnostic audio (ffmpeg/ffprobe/opus)")
    async def voice_diag(self, ctx: commands.Context):
        import discord.opus
        ffmpeg_bin = os.getenv("FFMPEG_BIN", "ffmpeg")
        ffprobe_bin = os.getenv("FFPROBE_BIN", "ffprobe")

        # test opus
        opus_loaded = discord.opus.is_loaded()
        try:
            if not opus_loaded:
                discord.opus.load_opus('libopus.so.0')
                opus_loaded = discord.opus.is_loaded()
        except Exception:
            pass

        # test versions
        def _cmd_ok(cmd):
            try:
                p = subprocess.run([cmd, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
                return p.returncode == 0
            except Exception:
                return False

        ok_ffmpeg = _cmd_ok(ffmpeg_bin)
        ok_ffprobe = _cmd_ok(ffprobe_bin)

        em = discord.Embed(
            title="🔊 Voice Diag",
            color=discord.Color.green() if (ok_ffmpeg and ok_ffprobe and opus_loaded) else discord.Color.red()
        )
        em.add_field(name="FFMPEG_BIN", value=f"`{ffmpeg_bin}` — {'✅' if ok_ffmpeg else '❌'}", inline=False)
        em.add_field(name="FFPROBE_BIN", value=f"`{ffprobe_bin}` — {'✅' if ok_ffprobe else '❌'}", inline=False)
        em.add_field(name="Opus", value="✅ chargé" if opus_loaded else "❌ non chargé", inline=False)
        await ctx.send(embed=em)

async def setup(bot: commands.Bot):
    await bot.add_cog(Openings(bot))
