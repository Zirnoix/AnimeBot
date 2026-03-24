# cogs/openings.py
from __future__ import annotations
import logging
import os
import random
import asyncio
import re
import tempfile
from typing import List
import json
import subprocess
import time

import aiohttp
import discord
from discord.ext import commands, tasks

from modules import core
from modules import voice              # ensure_connected + make_source précis/robuste
from modules import animethemes        # provider AnimeThemes + filtres AniList
from modules import guessop_catalog as gopc

LOG = logging.getLogger(__name__)

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
) -> discord.Embed:
    em = discord.Embed(
        title="🎵 Devine l’opening !",
        description=f"{_bar(remaining_sec, ANSWER_TIMEOUT)}  **{remaining_sec}s** restantes.\nClique sur **1–4** pour répondre.",
        color=discord.Color.purple()
    )
    for i, title in enumerate(choices, 1):
        em.add_field(name=f"{i}️⃣", value=title, inline=False)
    if responders:
        names = ", ".join(responders[:30])
        if len(responders) > 30:
            names += f" … (+{len(responders) - 30})"
        em.add_field(name="Déjà répondu", value=names, inline=False)
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
    ):
        super().__init__(timeout=timeout_sec)
        self.bot = bot
        self.ctx = ctx
        self.voice_channel = voice_channel
        self.choices = choices
        self.correct_index = correct_index
        self.source_footer = source_footer
        self.already_answered: set[int] = set()
        self.responders: list[str] = []
        self._remaining = timeout_sec
        self._embed_lock = asyncio.Lock()
        self.winners_order: list[discord.Member] = []
        self.others_correct: list[discord.Member] = []
        self._lock = asyncio.Lock()
        self.message: discord.Message | None = None

        for i in range(4):
            self.add_item(GuessOPButton(i))

    async def _update_responders_embed(self) -> None:
        async with self._embed_lock:
            if not self.message:
                return
            try:
                em = _build_question_embed(
                    self.choices,
                    self._remaining,
                    self.source_footer,
                    self.responders,
                )
                await self.message.edit(embed=em, view=self)
            except Exception:
                pass

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
            view.responders.append(interaction.user.display_name)

            if self.index == view.correct_index:
                if len(view.winners_order) < 3:
                    view.winners_order.append(interaction.user)
                    await interaction.response.send_message("✅ Bonne réponse !", ephemeral=True)
                    try:
                        await view.ctx.send(f"✅ {interaction.user.mention} a trouvé !")
                    except Exception:
                        pass
                else:
                    view.others_correct.append(interaction.user)
                    await interaction.response.send_message("✅ Bonne réponse (hors podium) !", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Mauvaise réponse.", ephemeral=True)

        asyncio.create_task(view._update_responders_embed())

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
        """Enrichit lentement le catalogue via l’API AnimeThemes (global, même base pour tous les serveurs)."""
        if not USE_ANIMETHEMES:
            return
        before = gopc.count()
        for _ in range(35):
            try:
                got = await animethemes.random_opening()
                if got:
                    t, th, url = got
                    if url.startswith(("http://", "https://")):
                        gopc.add_opening(t, th, url, "harvest_auto")
            except Exception:
                pass
            await asyncio.sleep(2.0)
        after = gopc.count()
        if after > before:
            LOG.info("Guess OP harvest : catalogue %d → %d (+%d)", before, after, after - before)

    @guessop_catalog_harvest.before_loop
    async def _before_guessop_harvest(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(180)

    @commands.hybrid_command(
        name="guessop",
        description="Devine l'opening (20s audio + 4 choix, catalogue global enrichi automatiquement)",
    )
    @commands.cooldown(1, 15, commands.BucketType.user)  # anti-spam: 1 commande / 15s par user
    async def guess_op(self, ctx: commands.Context) -> None:
        # Anti-timeout pour slash
        if getattr(ctx, "interaction", None):
            try:
                await ctx.interaction.response.defer()
            except Exception:
                pass

        send = (ctx.interaction.followup.send if getattr(ctx, "interaction", None) else ctx.send)

        # Vérif vocal
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await send("🔇 Tu dois être dans un **salon vocal** pour jouer.")
        voice_channel: discord.VoiceChannel = ctx.author.voice.channel

        async with self._guild_lock(ctx.guild.id):
            correct_anime = None
            theme_label = None
            media_source = None
            source_footer = ""

            # --------- 1) Catalogue persistant (prioritaire quand assez riche) ---------
            n_cat = gopc.count()
            if n_cat >= CATALOG_MIN_FOR_BIAS and random.random() < CATALOG_PICK_BIAS:
                picked = gopc.pick_random()
                if picked:
                    oid, correct_anime, theme_label, media_source = picked
                    source_footer = f"Catalogue Guess OP · {n_cat} openings"
                    gopc.record_used(oid)

            # --------- 2) Sinon AnimeThemes (+ ajout au catalogue) ---------
            if not media_source:
                got = None
                if USE_ANIMETHEMES:
                    try:
                        got = await animethemes.random_opening_filtered(
                            min_year=MIN_YEAR,
                            min_score_10=MIN_SCORE_10,
                            banned_genres=BANNED_GENRES,
                            banned_formats=BANNED_FORMATS,
                            max_attempts=12,
                        )
                    except Exception:
                        got = None

                    if got:
                        title, theme_label, video_url = got
                        correct_anime = title
                        media_source = video_url
                        source_footer = "Source : AnimeThemes.moe → ajout catalogue"
                        if video_url.startswith(("http://", "https://")):
                            gopc.add_opening(correct_anime, theme_label or "OP", video_url, "animethemes_live")

            # --------- 3) Fallback local ---------
            if not media_source:
                if not os.path.exists(LOCAL_AUDIO_FOLDER):
                    return await send("❌ Aucun opening trouvé (AnimeThemes vide + pas de dossier local).")
                files = [f for f in os.listdir(LOCAL_AUDIO_FOLDER) if f.lower().endswith(".mp3")]
                if not files:
                    return await send("❌ Aucun opening trouvé dans le dossier local.")
                pick = random.choice(files)
                media_source = os.path.join(LOCAL_AUDIO_FOLDER, pick)
                correct_anime = _clean_title_from_filename(pick)
                source_footer = "Source : fichiers locaux"

            # --------- 4) Génération des choix (leurres via AniList) ---------
            cache_key = "popular_romaji_60"
            pool = _get_cached_titles(cache_key)
            if pool is None:
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
                    data = core.query_anilist(query)
                    pool = [m["title"]["romaji"] for m in data["data"]["Page"]["media"]]
                    _set_cached_titles(cache_key, pool)
                except Exception:
                    pool = []

            choices = [correct_anime]
            tries = 0
            while len(choices) < 4 and pool and tries < 200:
                alt = _clean_title_from_filename(random.choice(pool))
                tries += 1
                if alt and alt.lower() != correct_anime.lower() and alt not in choices:
                    choices.append(alt)
            while len(choices) < 4:
                choices.append(f"Option {len(choices) + 1}")
            random.shuffle(choices)
            correct_index = choices.index(correct_anime)

            # --------- 5) Envoi question + boutons ---------
            em = _build_question_embed(choices, ANSWER_TIMEOUT, source_footer, [])
            view = GuessOPView(
                self.bot,
                ctx,
                voice_channel,
                choices,
                correct_index,
                timeout_sec=ANSWER_TIMEOUT,
                source_footer=source_footer,
            )
            sent = await send(embed=em, view=view)
            if isinstance(sent, discord.Message):
                view.message = sent

            # --------- 6) Connexion immédiate + Préparation audio en parallèle ---------
            try:
                vc = await voice.ensure_connected(voice_channel)
            except Exception as e:
                return await send(f"❌ Impossible de rejoindre le vocal : {e}")

            async def _prepare_local_file():
                local_path = media_source
                cleanup = False
                if isinstance(media_source, str) and media_source.startswith(("http://", "https://")):
                    local_path = await _fetch_to_temp(media_source)
                    cleanup = True
                return local_path, cleanup

            prepare_task = asyncio.create_task(_prepare_local_file())

            # --------- 7) Compte à rebours visuel (edit toutes les 5s) ---------
            async def _tick_embed():
                remaining = ANSWER_TIMEOUT
                while remaining > 0 and not view.is_finished() and view.message:
                    await asyncio.sleep(COUNTDOWN_STEP)
                    remaining = max(0, remaining - COUNTDOWN_STEP)
                    view._remaining = remaining
                    try:
                        async with view._embed_lock:
                            await view.message.edit(
                                embed=_build_question_embed(
                                    choices, remaining, source_footer, view.responders
                                ),
                                view=view,
                            )
                    except Exception:
                        break

            countdown_task = asyncio.create_task(_tick_embed())

            # --------- 8) Timer de fin de manche (borne dure UI) ---------
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

            # --------- 9) Lecture AUDIO pile DURATION_SEC (seek sécurisé + guard démarrage) ---------
            local_path = None
            cleanup = False

            try:
                local_path, cleanup = await prepare_task
                if not vc.is_connected():
                    vc = await voice.ensure_connected(voice_channel)

                # Sondage de durée + seek borné (toujours)
                media_duration = _probe_duration_sec(local_path)
                seek_start = _safe_seek(media_duration, DURATION_SEC, RANDOM_SEEK_MAX) if ENABLE_RANDOM_SEEK else 0.0

                # Source FFmpeg robuste (map audio + PCM + fades + coupe précise)
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

                # --- Guard de démarrage : on s'assure que le son part vraiment ---
                started = False
                for _ in range(int(START_GUARD_TIMEOUT / 0.1)):
                    await asyncio.sleep(0.1)
                    if vc.is_playing():
                        started = True
                        break

                # Si pas démarré ET on avait un seek => retry immédiat SANS seek
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

                    # Guard bis
                    for _ in range(int(START_GUARD_TIMEOUT / 0.1)):
                        await asyncio.sleep(0.1)
                        if vc.is_playing():
                            started = True
                            break

                # Attendre la fin avec marge (évite les 5s tronquées)
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

            # --------- 10) Fin de manche (= dès que la View se termine) ---------
            try:
                await view.wait()
            except Exception:
                pass

            # Annule les tâches encore actives
            if not end_timer_task.done():
                end_timer_task.cancel()
            if not countdown_task.done():
                countdown_task.cancel()

            # Déconnexion après affichage du résultat (propre)
            try:
                if vc and vc.is_connected():
                    await vc.disconnect(force=False)
            except Exception:
                pass

            # --------- 11) Résultat ---------
            if not view.winners_order and not view.others_correct:
                return await send(f"⏰ Temps écoulé ! La bonne réponse était : **{correct_anime}**")

            podium_xp = [15, 10, 7]
            others_xp = 3
            award_lines = []
            for rank, user in enumerate(view.winners_order, start=1):
                xp = podium_xp[rank-1]
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

            # ⚡ Plus rapide = premier du podium
            fast_line = f"⚡ Plus rapide : {view.winners_order[0].mention}" if view.winners_order else None

            res = discord.Embed(
                title="🏁 Résultats — Guess OP",
                description=f"✅ **Réponse :** {correct_anime}",
                color=discord.Color.gold()
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

            # Nettoyage auto après 30s (optionnel) — supprime le message de question
            try:
                await asyncio.sleep(30)
                if view.message:
                    await view.message.delete()
            except Exception:
                pass

    @commands.hybrid_command(name="guessopdb", description="(Owner) Statistiques du catalogue Guess OP")
    @commands.is_owner()
    async def guessop_db(self, ctx: commands.Context) -> None:
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(ephemeral=True)
        st = gopc.stats()
        lines = "\n".join(f"• **{s}** : {c}" for s, c in st.get("by_source", [])) or "—"
        top = gopc.top_used(5)
        top_txt = "\n".join(f"• {t} — {u}×" for t, u in top) if top else "—"
        em = discord.Embed(
            title="📚 Catalogue Guess OP",
            description=f"**{st['total']}** openings uniques (URL) — même base sur **tous** les serveurs.",
            color=discord.Color.blue(),
        )
        em.add_field(name="Par source", value=lines[:1024], inline=False)
        em.add_field(name="Plus tirés", value=top_txt[:1024], inline=False)
        await ctx.send(embed=em)

    @commands.hybrid_command(
        name="guessopharvest",
        description="(Owner) Enrichit vite le catalogue via AnimeThemes (~1–2 min)",
    )
    @commands.is_owner()
    async def guessop_harvest_manual(self, ctx: commands.Context) -> None:
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(ephemeral=True)
        before = gopc.count()
        for _ in range(45):
            try:
                got = await animethemes.random_opening()
                if got:
                    t, th, url = got
                    if url.startswith(("http://", "https://")):
                        gopc.add_opening(t, th, url, "manual_harvest")
            except Exception:
                pass
            await asyncio.sleep(1.2)
        after = gopc.count()
        await ctx.send(f"✅ Catalogue : **{before}** → **{after}** openings (URLs uniques).")

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
