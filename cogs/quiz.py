"""
Quiz and duel commands (AniList live).

- /animequiz  (choices de difficulté) — après la manche, message optionnel « Ajouter au suivi » pour tous
- /animequizmulti
- /duel       (choices manches + difficulté)
- /quiztop
- /quizlevels
- /myrank

Tirage d'anime en direct depuis AniList avec filtres:
  - countryOfOrigin: JP
  - startDate.year >= 1985
  - averageScore >= 5/10 (modifiable)
  - isAdult = False
"""

from __future__ import annotations

import random
import asyncio
import logging
import time
import difflib
from datetime import datetime, timedelta, timezone
from typing import Optional, Set, Dict, List, Any

import discord
from discord.ext import commands
from discord import app_commands

from modules import anilist_gate
from modules import core, i18n
from modules import user_reply
from modules import minigame_lock
from modules.core import normalize

logger = logging.getLogger(__name__)


def _embed_footer_anilist_hint(ctx: commands.Context, genres: Optional[List[str]] = None) -> str:
    """Pied d’embed quiz : genres + rappel compte AniList lié ou /linkanilist."""
    parts: List[str] = []
    if genres:
        parts.append(f"Genres : {', '.join(genres)}")
    alu = core.get_linked_username(ctx.author.id)
    if alu:
        parts.append(f"AniList lié : {alu}")
    else:
        parts.append("/linkanilist pour lier ton profil")
    return " · ".join(parts)[:2048]

# --- petit utilitaire pour éviter "This interaction failed" côté slash ---
async def _maybe_defer(ctx: commands.Context, ephemeral: bool = False) -> None:
    await core.maybe_defer_hybrid(ctx, ephemeral=ephemeral)

# --- paramètres DUEL ---
ANSWER_TIMEOUT = 25  # secondes par manche
IGNORED_ANSWERS: Set[str] = {"jsp", "je sais pas", "idk", "skip", "pass", "aucune idée", "dk"}
_active_duels_per_channel: Dict[int, bool] = {}  # anti-chevauchement par salon

# Cooldown après la fin d’un duel (secondes) — les deux joueurs sont marqués.
DUEL_COOLDOWN_AFTER_SEC = 10.0
_last_duel_end_by_user: dict[int, float] = {}


def _duel_cooldown_remaining(uid: int) -> float:
    t = _last_duel_end_by_user.get(uid)
    if t is None:
        return 0.0
    return max(0.0, DUEL_COOLDOWN_AFTER_SEC - (time.monotonic() - t))


def _mark_duel_ended(uid_a: int, uid_b: int) -> None:
    now = time.monotonic()
    _last_duel_end_by_user[uid_a] = now
    _last_duel_end_by_user[uid_b] = now


def _is_jsp(guess: str) -> bool:
    """Réponse type « je passe » (jsp) pour le duel — aligné sur IGNORED_ANSWERS."""
    return (guess or "").strip().lower() in IGNORED_ANSWERS


class AnimequizTrackOfferView(discord.ui.View):
    """
    Bouton « ajouter au suivi » sur le message de fin de /animequiz : visible par tout le monde,
    chaque clic ajoute la série au suivi **du joueur qui clique** (même logique que /track add).
    Au timeout (~1 min), le message est supprimé (ou la vue retirée si suppression impossible).
    """

    def __init__(self, romaji_title: str) -> None:
        super().__init__(timeout=60.0)
        self.romaji_title = romaji_title

    async def on_timeout(self) -> None:
        msg = self.message
        if msg is None:
            return
        try:
            await msg.delete()
        except (discord.HTTPException, discord.NotFound):
            try:
                await msg.edit(view=None)
            except Exception:
                pass

    @discord.ui.button(label="Ajouter à mon suivi", style=discord.ButtonStyle.success, emoji="📌", row=0)
    async def add_to_track(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        title = self.romaji_title
        tracker = core.load_tracker()
        uid = str(interaction.user.id)
        lst = tracker.setdefault(uid, [])
        nrm = normalize(title)
        if any(normalize(t) == nrm for t in lst):
            await interaction.response.send_message(
                "ℹ️ Tu **suivis déjà** cette série.",
                ephemeral=True,
            )
            return
        lst.append(title)
        tracker[uid] = lst
        core.save_tracker(tracker)
        await interaction.response.send_message(
            f"✅ **{title}** ajouté à ton suivi — tu recevras un **MP** quand un épisode sort.",
            ephemeral=True,
        )


async def _send_animequiz_track_offer(ctx: commands.Context, anime: Dict[str, Any]) -> None:
    """Après une manche d’/animequiz, propose d’ajouter l’anime au tracker personnel."""
    romaji = (anime.get("title") or {}).get("romaji")
    if not romaji:
        return
    embed = discord.Embed(
        title="🔔 Suivi des sorties",
        description=(
            f"Série : **{romaji}**\n\n"
            "Ajoute-la à **ta** liste personnelle : **alerte en MP** quand un épisode sort (comme **`/track add`**).\n"
            "**Tout le monde** peut utiliser le bouton : chacun ajoute à **son** suivi."
        ),
        color=discord.Color.teal(),
    )
    cov = (anime.get("coverImage") or {}).get("large") or (anime.get("coverImage") or {}).get("extraLarge")
    if cov:
        embed.set_thumbnail(url=cov)
    embed.set_footer(text="Anime quiz · ce message disparaît après 1 min · /track list")
    try:
        view = AnimequizTrackOfferView(romaji)
        msg = await ctx.send(embed=embed, view=view)
        # Référence explicite pour on_timeout (suppression du message)
        view.message = msg
    except Exception:
        pass


# --- filtres AnimeQuiz ---
ANI_MIN_YEAR   = 1985
ANI_MIN_SCORE  = 50   # 50 = 5/10 ; mets 40 si tu veux 4/10
ANI_IS_ADULT   = False

# mapping difficulté → tri AniList
SORT_BY_DIFF = {
    "easy":   "POPULARITY_DESC",
    "medium": "SCORE_DESC",
    "hard":   "TRENDING_DESC",
}

def _next_reset_dt(tz) -> datetime:
    now = datetime.now(tz)
    year = now.year + (1 if now.month == 12 else 0)
    month = 1 if now.month == 12 else now.month + 1
    return datetime(year, month, 1, 0, 0, tzinfo=tz)

def _human_td(delta: timedelta) -> str:
    s = max(0, int(delta.total_seconds()))
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m, _ = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}j")
    if h: parts.append(f"{h}h")
    if m or not parts: parts.append(f"{m}m")
    return " ".join(parts)


class TitleMatcher:
    """Gestionnaire de correspondance des titres d'anime."""

    # Avant `normalize` : sinon « Kaguya-sama » → « kaguyasama » alors que l’utilisateur tape « kaguya sama ».
    _SEP_BEFORE_NORM = (
        "-",
        "\u2010",
        "\u2011",
        "\u2012",
        "\u2013",
        "\u2014",
        "\u2015",
        "\uFF0D",
        ":",
        "?",
        "!",
        "…",
        "/",
        "|",
        "(",
        ")",
        "[",
        "]",
    )

    def __init__(self):
        self.cached_titles: Dict[str, Set[str]] = {}

    @classmethod
    def _prepare_for_normalize(cls, raw: str) -> str:
        t = raw or ""
        for sep in cls._SEP_BEFORE_NORM:
            t = t.replace(sep, " ")
        while "  " in t:
            t = t.replace("  ", " ")
        return t.strip()

    def clean_title(self, title: str) -> str:
        cleaned = core.normalize(self._prepare_for_normalize(title))
        stop_words = {"the", "a", "an", "season", "part", "episode", "movie", "saison"}
        words = [w for w in cleaned.split() if w not in stop_words]
        return " ".join(words)

    def get_similarity(self, str1: str, str2: str) -> float:
        return difflib.SequenceMatcher(None, str1, str2).ratio()

    def find_matches(self, guess: str, correct_titles: Set[str], threshold: float = 0.85) -> List[str]:
        cleaned_guess = self.clean_title(guess)
        # Emojis / ponctuation seule → normalize vide ; "" in "n'importe quel titre" est True en Python.
        if not cleaned_guess:
            return []
        matches: List[str] = []
        for title in correct_titles:
            cleaned_title = self.clean_title(title)
            if cleaned_guess == cleaned_title:
                return [title]
            # Sous-chaîne : exiger au moins 2 caractères pour éviter les faux positifs (ex. "" ou "a").
            if len(cleaned_guess) >= 2 and (
                cleaned_guess in cleaned_title or cleaned_title in cleaned_guess
            ):
                matches.append(title)
                continue
            if len(cleaned_guess) >= 2 and self.get_similarity(cleaned_guess, cleaned_title) >= threshold:
                matches.append(title)
        return matches


class DuelInviteView(discord.ui.View):
    """Vue d'invitation : l'adversaire peut accepter ou refuser."""
    def __init__(self, challenger: discord.Member, opponent: discord.Member, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.challenger = challenger
        self.opponent = opponent
        self.accepted: Optional[bool] = None
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        if self.message and self.accepted is None:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            try:
                await self.message.edit(content="⌛ Invitation expirée.", view=self)
            except Exception:
                pass

    async def _only_opponent(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Seul l’adversaire peut répondre à cette invitation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._only_opponent(interaction):
            return
        self.accepted = True
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(content=f"✅ **{self.opponent.display_name}** a accepté le duel !", view=self)
        self.stop()

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._only_opponent(interaction):
            return
        self.accepted = False
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(content=f"🚫 **{self.opponent.display_name}** a refusé le duel.", view=self)
        self.stop()


class QuizLevelsSelect(discord.ui.Select):
    """Menu : titres quiz (score du mois) ou rangs XP globaux (/profile)."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Choisir quel palier afficher…",
            options=[
                discord.SelectOption(
                    label="Titres quiz (score du mois)",
                    value="quiz",
                    emoji="🎯",
                    default=True,
                ),
                discord.SelectOption(
                    label="Rangs XP globaux (/profile)",
                    value="xp",
                    emoji="🌟",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.view
        if not isinstance(parent, QuizLevelsView):
            await interaction.response.send_message(
                "Ce menu a expiré — refais **`/quizlevels`**.",
                ephemeral=True,
            )
            return
        key = (self.values[0] if self.values else "quiz") or "quiz"
        emb = parent._quiz_embed if key == "quiz" else parent._xp_embed
        await interaction.response.edit_message(embed=emb, view=parent)


class QuizLevelsView(discord.ui.View):
    def __init__(self, author_id: int, quiz_embed: discord.Embed, xp_embed: discord.Embed) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self._quiz_embed = quiz_embed
        self._xp_embed = xp_embed
        self.add_item(QuizLevelsSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce menu n’est pas pour toi.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            if isinstance(c, discord.ui.Select):
                c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class Quiz(commands.Cog):
    """Cog for anime quiz commands (AniList live)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.title_matcher = TitleMatcher()

    # ---------- AniList live picker ----------
    async def _fetch_random_anilist_media(
        self,
        sort: str,
        *,
        queue_ctx: Optional[commands.Context] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Tire un anime aléatoire depuis AniList avec filtres,
        en choisissant une page au hasard pour varier les résultats.
        """
        # 1) Récupérer le nombre de pages (avec un lot léger)
        query_count = """
        query ($page: Int, $perPage: Int, $sort: [MediaSort], $minYear: FuzzyDateInt, $minScore: Int, $adult: Boolean) {
          Page(page: $page, perPage: $perPage) {
            pageInfo { total perPage currentPage lastPage }
            media(
              type: ANIME
              sort: $sort
              isAdult: $adult
              countryOfOrigin: JP
              averageScore_greater: $minScore
              startDate_greater: $minYear
            ) { id }
          }
        }
        """
        variables = {
            "page": 1,
            "perPage": 50,
            "sort": [sort],
            "minYear": ANI_MIN_YEAR * 10000,  # FuzzyDateInt (YYYYMMDD)
            "minScore": ANI_MIN_SCORE,
            "adult": ANI_IS_ADULT,
        }
        data = await core.query_anilist_async(query_count, variables, queue_ctx=queue_ctx) or {}
        try:
            page_info = data["data"]["Page"]["pageInfo"]
            last_page = int(page_info.get("lastPage") or 1)
            if last_page < 1:
                return None
        except Exception:
            return None

        # 2) Choisir une page aléatoire et prendre des champs utiles
        rnd_page = random.randint(1, last_page)
        query_pick = """
        query ($page: Int, $perPage: Int, $sort: [MediaSort], $minYear: FuzzyDateInt, $minScore: Int, $adult: Boolean) {
          Page(page: $page, perPage: $perPage) {
            media(
              type: ANIME
              sort: $sort
              isAdult: $adult
              countryOfOrigin: JP
              averageScore_greater: $minScore
              startDate_greater: $minYear
            ) {
              id
              title { romaji english native }
              synonyms
              averageScore
              genres
              coverImage { large extraLarge }
              episodes
              seasonYear
              format
              nextAiringEpisode { episode airingAt }
              siteUrl
            }
          }
        }
        """
        variables.update({"page": rnd_page, "perPage": 25})
        data2 = await core.query_anilist_async(query_pick, variables, queue_ctx=queue_ctx) or {}
        try:
            media_list = data2["data"]["Page"]["media"] or []
        except Exception:
            media_list = []

        if not media_list:
            return None

        return random.choice(media_list)

    def _titles_set(self, anime: Dict[str, Any]) -> Set[str]:
        t = anime.get("title") or {}
        s: Set[str] = set()
        for k in ("romaji", "english", "native"):
            if t.get(k):
                s.add(t[k])
        for syn in (anime.get("synonyms") or []):
            if syn:
                s.add(syn)
        return s

    # ---------- COMMANDES HYBRIDES (slash + préfixe) ----------

    @commands.hybrid_command(name="animequiz", description="Devine l’anime à partir de son image.")
    @commands.cooldown(1, 15, commands.BucketType.user)
    @app_commands.describe(difficulty="Choisis la difficulté")
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="Easy 😌",   value="easy"),
            app_commands.Choice(name="Medium 😼", value="medium"),
            app_commands.Choice(name="Hard 🔥",   value="hard"),
        ]
    )
    async def animequiz(self, ctx: commands.Context, difficulty: str = "medium") -> None:
        uid = ctx.author.id
        await _maybe_defer(ctx)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "animequiz"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            await ctx.send("🎮 Préparation du quiz...")

            sort_option = SORT_BY_DIFF.get((difficulty or "medium").lower(), "SCORE_DESC")

            anime = await self._fetch_random_anilist_media(sort_option, queue_ctx=ctx)
            if not anime:
                await ctx.send(core.anilist_error_user_message())
                return

            correct_titles = self._titles_set(anime)

            embed = discord.Embed(
                title="❓ Quel est cet anime ?",
                description=(
                    "Tu as **20 secondes** pour deviner.\n"
                    "💡 Titres FR/EN/JP acceptés. Tape `jsp` pour passer."
                ),
                color=discord.Color.orange(),
            )
            image_url = (anime.get("coverImage", {}) or {}).get("extraLarge") or (anime.get("coverImage", {}) or {}).get("large")
            if image_url:
                embed.set_image(url=image_url)
            genres = anime.get("genres") or []
            embed.set_footer(text=_embed_footer_anilist_hint(ctx, genres if genres else None))
            await ctx.send(embed=embed)

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=20.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                )
                guess = (msg.content or "").strip()

                if guess.lower() == "jsp":
                    lines = [
                        f"🇯🇵 {anime['title'].get('romaji')}",
                        f"🇬🇧 {anime['title'].get('english')}" if anime['title'].get('english') else None,
                        f"📝 {anime['title'].get('native')}" if anime['title'].get('native') else None,
                    ]
                    lines = [x for x in lines if x]
                    await ctx.send("⏭️ Passé.\n" + "\n".join(lines))
                    await _send_animequiz_track_offer(ctx, anime)
                    return

                if self.title_matcher.find_matches(guess, correct_titles):
                    await ctx.send(f"✅ Bonne réponse, **{ctx.author.display_name}** !")

                    # scoreboard + xp
                    with core.DATA_JSON_LOCK:
                        scores = core.load_scores()
                        uid_str = str(ctx.author.id)
                        old_q = int(scores.get(uid_str, 0))
                        scores[uid_str] = old_q + 1
                        new_q = scores[uid_str]
                        core.save_scores(scores)
                    await core.announce_quiz_title_if_changed(self.bot, ctx.channel, ctx.author.id, old_q, new_q)

                    xp_amount = 5 if difficulty == "easy" else 10 if difficulty == "medium" else 15
                    await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp_amount)
                    core.add_mini_score(ctx.author.id, "animequiz", 1)

                    # Missions
                    ctx.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_win")
                    ctx.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_solo_ok")

                    other_titles = [t for t in correct_titles if normalize(t) != normalize(guess)]
                    if other_titles:
                        await ctx.send(f"💡 Autres titres acceptés : {', '.join(other_titles)}")
                    await _send_animequiz_track_offer(ctx, anime)
                else:
                    await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title'].get('romaji')}**.")
                    await _send_animequiz_track_offer(ctx, anime)

            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était **{anime['title'].get('romaji')}**.")
                await _send_animequiz_track_offer(ctx, anime)

        except Exception as e:
            logger.error(f"Erreur dans animequiz: {e}")
            await ctx.send("❌ Une erreur s'est produite lors du quiz.")
        finally:
            minigame_lock.end(uid)

    @commands.hybrid_command(name="animequizmulti", description="Quiz multi (5 à 20 questions) — easy/medium/hard aléatoires.")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(nb_questions="Nombre de questions (5 à 20)")
    async def animequizmulti(
        self,
        ctx: commands.Context,
        nb_questions: app_commands.Range[int, 5, 20] = 5,
    ) -> None:
        uid = ctx.author.id
        await _maybe_defer(ctx)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "animequizmulti"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            if not 5 <= nb_questions <= 20:
                await ctx.send("❌ Choisis un nombre entre **5** et **20**.")
                return

            await ctx.send(f"🎮 Lancement de **{nb_questions} questions**…")
            diffs = ["easy", "medium", "hard"]
            score = 0
            total_xp = 0
            combo = 0
            combo_bonus_total = 0
            rounds_with_anime = 0

            for i in range(nb_questions):
                try:
                    difficulty = random.choice(diffs)
                    sort_option = SORT_BY_DIFF.get(difficulty, "SCORE_DESC")

                    anime = await self._fetch_random_anilist_media(sort_option, queue_ctx=ctx)
                    if not anime:
                        await asyncio.sleep(0.6)
                        continue
                    rounds_with_anime += 1

                    correct_titles = self._titles_set(anime)
                    image = (anime.get("coverImage", {}) or {}).get("extraLarge") or (anime.get("coverImage", {}) or {}).get("large")

                    embed = discord.Embed(
                        title=f"❓ Q{i+1}/{nb_questions} — difficulté `{difficulty}`",
                        description="Tu as **20s**. Tape `jsp` pour passer.",
                        color=discord.Color.orange(),
                    )
                    if image:
                        embed.set_image(url=image)
                    embed.set_footer(
                        text=_embed_footer_anilist_hint(ctx, list(anime.get("genres") or []))
                    )
                    await ctx.send(embed=embed)

                    try:
                        msg = await self.bot.wait_for(
                            "message",
                            timeout=20.0,
                            check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                        )
                        guess = msg.content.strip()

                        if guess.lower() == "jsp":
                            await ctx.send(f"⏭️ Passé. C’était **{anime['title'].get('romaji')}**.")
                            combo = 0
                        else:
                            if self.title_matcher.find_matches(guess, correct_titles):
                                tshow = core.format_anilist_title_obj(anime.get("title"))
                                await ctx.send(f"✅ Bonne réponse ! — **{tshow}**")
                                score += 1
                                xp_gain = 5 if difficulty == "easy" else 10 if difficulty == "medium" else 15
                                total_xp += xp_gain
                                core.add_mini_score(ctx.author.id, "animequiz", 1)
                                combo += 1
                                if combo == 3:
                                    combo_bonus_total += 2
                                    await ctx.send("✨ **Combo x3 !** +2 XP bonus")
                                elif combo == 5:
                                    combo_bonus_total += 5
                                    await ctx.send("🌟 **Combo x5 !** +5 XP bonus")
                            else:
                                await ctx.send(f"❌ Faux ! C’était **{anime['title'].get('romaji')}**.")
                                combo = 0

                    except asyncio.TimeoutError:
                        await ctx.send(f"⏰ Temps écoulé ! C’était **{anime['title'].get('romaji')}**.")
                        combo = 0

                except Exception as e:
                    logger.error(f"Erreur question {i + 1}: {e}")
                    continue

                await asyncio.sleep(1.2)

            if rounds_with_anime == 0:
                await ctx.send(
                    "📡 **Aucune question** n’a pu être chargée (AniList indisponible ou dégradé). "
                    "**Aucun point** de classement quiz n’a été modifié."
                )
                return

            # scoreboard global
            penalty = 0
            with core.DATA_JSON_LOCK:
                scores = core.load_scores()
                uid_str = str(ctx.author.id)
                old_q = int(scores.get(uid_str, 0))
                if score < (rounds_with_anime / 2):
                    penalty = 1
                    scores[uid_str] = max(0, old_q - penalty)
                else:
                    scores[uid_str] = old_q + score
                new_q = int(scores[uid_str])
                core.save_scores(scores)
            if penalty:
                await ctx.send(f"⚠️ Moins de 50% de bonnes réponses sur les questions jouées, -{penalty} point retiré.")
            await core.announce_quiz_title_if_changed(self.bot, ctx.channel, ctx.author.id, old_q, new_q)

            total_xp += combo_bonus_total
            if total_xp > 0:
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, total_xp)

            precision = (score / rounds_with_anime * 100) if rounds_with_anime > 0 else 0.0
            # Mission: win multi si ≥ 50%
            if score >= max(1, rounds_with_anime // 2):
                self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_win")

            embed = discord.Embed(
                title="🏁 Quiz terminé !",
                description=(
                    f"Score final : **{score}/{rounds_with_anime}** questions jouées "
                    f"(sur **{nb_questions}** prévues)\n"
                    f"XP gagnés : **{total_xp}** *(dont **{combo_bonus_total}** en combos)*\n"
                    f"Précision : **{precision:.1f}%**"
                ),
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans animequizmulti: {e}")
            await ctx.send("❌ Une erreur s'est produite durant le quiz.")
        finally:
            minigame_lock.end(uid)

    # ---------- DUEL AMÉLIORÉ ----------
    @commands.hybrid_command(
        name="duel",
        description="Affronte un ami en duel (manches & difficulté)."
    )
    @app_commands.rename(opponent="adversaire", manches="manches", difficulte="difficulte")
    @app_commands.describe(
        opponent="La personne que tu défies",
        manches="Nombre de manches (1–10)",
        difficulte="Choisis la difficulté"
    )
    @app_commands.choices(
        manches=[app_commands.Choice(name=str(i), value=i) for i in range(1, 11)],
        difficulte=[
            app_commands.Choice(name="Easy 😌",   value="easy"),
            app_commands.Choice(name="Medium 😼", value="medium"),
            app_commands.Choice(name="Hard 🔥",   value="hard"),
        ]
    )
    async def duel(
        self,
        ctx: commands.Context,
        opponent: discord.Member,
        manches: int,
        difficulte: str,
    ) -> None:
        """Invitation + duel : 1–10 manches, difficulté easy/medium/hard,
        premier bon = point, 'jsp' = pass ; si les 2 disent 'jsp' => skip immédiat avec reveal.
        """
        duel_started = False
        try:
            await _maybe_defer(ctx)
            if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
                return

            # Garde-fous
            if opponent.bot:
                await ctx.send("🤖 Tu ne peux pas défier un bot.")
                return
            if opponent.id == ctx.author.id:
                await ctx.send("🙃 Tu ne peux pas te défier toi-même.")
                return

            for uid in (ctx.author.id, opponent.id):
                left = _duel_cooldown_remaining(uid)
                if left > 0:
                    await user_reply.send_ephemeral_or_private(
                        ctx,
                        f"⏳ Attends encore **{int(left) + 1}s** après la fin du dernier duel "
                        f"(toi ou ton adversaire).",
                    )
                    return
    
            manches = max(1, min(int(manches), 10))
            diff = (difficulte or "medium").lower()
            sort_option = SORT_BY_DIFF.get(diff, "SCORE_DESC")
    
            # Verrou par salon
            channel_id = ctx.channel.id
            if _active_duels_per_channel.get(channel_id):
                await ctx.send("⏳ Un duel est déjà en cours dans ce salon. Réessaie après.")
                return
            _active_duels_per_channel[channel_id] = True
    
            # Invitation
            invite_view = DuelInviteView(challenger=ctx.author, opponent=opponent, timeout=45)
            msg = await ctx.send(
                content=(
                    f"⚔️ **{ctx.author.mention}** défie **{opponent.mention}** !\n"
                    f"Manches : **{manches}** — Difficulté : **{diff}**\n"
                    f"{opponent.mention}, acceptes-tu ce duel ?"
                ),
                view=invite_view
            )
            invite_view.message = msg
    
            await invite_view.wait()
            if invite_view.accepted is not True:
                if invite_view.accepted is None:
                    await ctx.send("⌛ Aucune réponse : invitation expirée.")
                return

            duel_started = True
    
            # OK duel
            players = (ctx.author, opponent)
            scores = {ctx.author.id: 0, opponent.id: 0}
    
            await ctx.send(
                f"✅ Duel accepté ! **{players[0].display_name}** vs **{players[1].display_name}** — "
                f"**{manches} manches**. Le **premier bon** gagne la manche.\n"
                f"⛔ Réponses ignorées : {', '.join(sorted(IGNORED_ANSWERS))}.\n"
                f"💡 Tape **jsp** pour passer ; si **les deux** passent → on révèle et on enchaîne."
            )
    
            for i in range(1, manches + 1):
                anime = await self._fetch_random_anilist_media(sort_option, queue_ctx=ctx)
                if not anime:
                    await ctx.send(core.anilist_error_user_message())
                    continue
    
                correct_titles = self._titles_set(anime)
                image = (anime.get("coverImage", {}) or {}).get("extraLarge") or (anime.get("coverImage", {}) or {}).get("large")
                genres = anime.get("genres", [])
    
                embed = discord.Embed(
                    title=f"🧩 Manche {i}/{manches}",
                    description=(
                        "**Le plus rapide à répondre correctement gagne !**\n"
                        f"⏱️ {ANSWER_TIMEOUT}s — titres FR/EN/JP acceptés."
                    ),
                    color=discord.Color.red(),
                )
                if image:
                    embed.set_image(url=image)
                embed.set_footer(text=_embed_footer_anilist_hint(ctx, genres if genres else None))
                await ctx.send(embed=embed)
    
                winner: Optional[discord.Member] = None
                jsp_flags = {players[0].id: False, players[1].id: False}
    
                def check(m: discord.Message) -> bool:
                    return (
                        m.channel == ctx.channel
                        and not m.author.bot
                        and m.author.id in (players[0].id, players[1].id)
                    )
    
                start = asyncio.get_event_loop().time()
                while True:
                    now = asyncio.get_event_loop().time()
                    left = ANSWER_TIMEOUT - (now - start)
                    if left <= 0:
                        break
                    try:
                        # small step timeout to re-check both-jsp quickly
                        msg: discord.Message = await self.bot.wait_for("message", timeout=min(2.0, max(0.1, left)), check=check)
                    except asyncio.TimeoutError:
                        continue  # loop to check timer
    
                    guess_raw = msg.content or ""
                    guess = guess_raw.strip()
    
                    # pass (jsp) → on marque le joueur et on check si les deux ont passé
                    if _is_jsp(guess):
                        if not jsp_flags[msg.author.id]:
                            jsp_flags[msg.author.id] = True
                            await ctx.send(f"↩️ {msg.author.mention} passe.")
                        if jsp_flags[players[0].id] and jsp_flags[players[1].id]:
                            # double pass ⇒ révélation + on quitte la manche sans vainqueur
                            winner = None
                            break
                        continue
    
                    # autres réponses ignorées (hors 'jsp', géré plus haut)
                    if guess.lower() in IGNORED_ANSWERS:
                        continue
    
                    # bonne réponse ?
                    if self.title_matcher.find_matches(guess, correct_titles):
                        winner = msg.author
                        break
    
                # Reveal titles
                titles_lines = [
                    f"🇯🇵 {anime['title'].get('romaji')}",
                    f"🇬🇧 {anime['title'].get('english')}" if anime['title'].get('english') else None,
                    f"📝 {anime['title'].get('native')}" if anime['title'].get('native') else None,
                ]
                titles_lines = [t for t in titles_lines if t]
                reveal = " / ".join(titles_lines) if titles_lines else "—"
    
                if winner:
                    scores[winner.id] += 1
                    await ctx.send(
                        f"✅ **{winner.display_name}** marque le point !\n"
                        f"Réponse acceptée : **{reveal}**\n"
                        f"🔢 Score: {players[0].display_name} {scores[players[0].id]} — "
                        f"{scores[players[1].id]} {players[1].display_name}"
                    )
                    try:
                        await core.add_xp(self.bot, ctx.channel, winner.id, 6)
                        core.add_mini_score(winner.id, "duel", 1)
                    except Exception:
                        pass
                else:
                    # Timeout OU double "jsp" ⇒ on révèle
                    await ctx.send(
                        f"{'⏰ Temps écoulé.' if not (jsp_flags[players[0].id] and jsp_flags[players[1].id]) else '⏭️ Les deux joueurs ont passé.'}\n"
                        f"Réponse attendue : **{reveal}**\n"
                        f"🔢 Score: {players[0].display_name} {scores[players[0].id]} — "
                        f"{scores[players[1].id]} {players[1].display_name}"
                    )
    
                await asyncio.sleep(1)
    
            s1, s2 = scores[players[0].id], scores[players[1].id]
            champ = players[0] if s1 > s2 else players[1] if s2 > s1 else None
    
            if champ:
                embed = discord.Embed(
                    title="🏆 Résultats du duel",
                    description=(
                        f"Victoire de **{champ.display_name}** !\n"
                        f"**{players[0].display_name}** {s1} - {s2} **{players[1].display_name}**\n"
                        f"🎖️ +20 XP au vainqueur"
                    ),
                    color=discord.Color.gold()
                )
                await ctx.send(embed=embed)
                try:
                    await core.add_xp(self.bot, ctx.channel, champ.id, 20)
                    core.add_mini_score(champ.id, "duel_victory", 1)
                except Exception:
                    pass
    
                # Mission : victoire de duel
                self.bot.dispatch("mission_progress", champ.id, "_custom:duel_win")
            else:
                await ctx.send(embed=discord.Embed(
                    title="🏁 Résultats du duel",
                    description=f"🤝 **Égalité** — {players[0].display_name} {s1} - {s2} {players[1].display_name}",
                    color=discord.Color.gold()
                ))
    
        except Exception as e:
            logger.error(f"Erreur dans duel: {e}")
            await ctx.send("❌ Une erreur s'est produite pendant le duel.")
        finally:
            _active_duels_per_channel.pop(ctx.channel.id, None)
            if duel_started:
                _mark_duel_ended(ctx.author.id, opponent.id)


    @commands.hybrid_command(name="quiztop", description="Top quiz du mois en cours + vainqueur du mois dernier.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def quiztop(self, ctx: commands.Context) -> None:
        try:
            await _maybe_defer(ctx, ephemeral=False)

            # Top du mois en cours
            scores = core.load_scores()  # {user_id_str: score_int}
            top10 = core.compute_quiz_top(scores, n=10)  # [(uid_str, score_int), ...]

            em = discord.Embed(
                title="🏆 Classement Quiz — Mois en cours",
                color=discord.Color.gold()
            )

            if not top10:
                em.description = "Aucun score pour l’instant."
            else:
                lines: List[str] = []
                medals = ["🥇", "🥈", "🥉"]
                for i, (uid, sc) in enumerate(top10, start=1):
                    badge = medals[i-1] if i <= 3 else f"#{i}"
                    display = f"<@{uid}>"
                    try:
                        member = ctx.guild.get_member(int(uid)) if ctx.guild else None
                        if not member:
                            member = await self.bot.fetch_user(int(uid))
                        if member:
                            display = member.display_name
                    except Exception:
                        pass
                    lines.append(f"{badge} **{display}** — {sc} pts")
                em.add_field(name="Top 10", value="\n".join(lines)[:1024], inline=False)

            # Mois dernier (écrit par quiz_reset) : podium + récompenses XP/badges envoyées en MP
            w = core.load_winner()
            if w and w.get("month"):
                label = core.human_month_fr(w["month"])
                podium = w.get("podium")
                if isinstance(podium, list) and podium:
                    lines_p: List[str] = []
                    medals = ["🥇", "🥈", "🥉"]
                    for row in sorted(podium, key=lambda r: int(r.get("rank") or 99))[:3]:
                        rk = int(row.get("rank") or 0)
                        uid = row.get("user_id")
                        sc = int(row.get("score") or 0)
                        if not uid:
                            continue
                        md = medals[rk - 1] if 1 <= rk <= 3 else f"#{rk}"
                        disp = f"<@{uid}>"
                        try:
                            mem = ctx.guild.get_member(int(uid)) if ctx.guild else None
                            if not mem:
                                mem = await self.bot.fetch_user(int(uid))
                            if mem:
                                disp = mem.display_name
                        except Exception:
                            pass
                        lines_p.append(f"{md} **{disp}** — {sc} pts")
                    if lines_p:
                        em.add_field(
                            name=f"🏅 Podium {label}",
                            value="\n".join(lines_p)[:1024],
                            inline=False,
                        )
                        em.add_field(
                            name="🎁 Récompenses",
                            value="**1ʳᵉ** +600 XP · **2ᵉ** +350 XP · **3ᵉ** +200 XP (MP + trophées).",
                            inline=False,
                        )
                else:
                    wid = w.get("winner_user_id")
                    wsc = int(w.get("winner_score") or 0)
                    if wid:
                        wname = f"<@{wid}>"
                        try:
                            member = ctx.guild.get_member(int(wid)) if ctx.guild else None
                            if not member:
                                member = await self.bot.fetch_user(int(wid))
                            if member:
                                wname = member.display_name
                        except Exception:
                            pass
                        em.add_field(name=f"🏅 Vainqueur {label}", value=f"**{wname}** — {wsc} pts", inline=False)
                    else:
                        em.add_field(name=f"🏅 Vainqueur {label}", value="Aucun vainqueur (pas de scores).", inline=False)

            # Compte à rebours vers le prochain reset (1er du mois 00:00)
            tz = getattr(core, "TIMEZONE", timezone.utc)
            nxt = _next_reset_dt(tz)
            left = _human_td(nxt - datetime.now(tz))
            ft = f"⏳ Prochain reset : {nxt:%d/%m %H:%M} • dans {left}"
            alu = core.get_linked_username(ctx.author.id)
            if alu:
                ft += f" · AniList : {alu}"
            else:
                ft += " · /linkanilist"
            em.set_footer(text=ft[:2048])

            await ctx.send(embed=em)

        except Exception as e:
            logger.error(f"Erreur dans quiztop: {e}")
            await ctx.send("❌ Une erreur s'est produite.")

    @commands.hybrid_command(
        name="quizlevels",
        description="Liste des paliers : menu pour choisir titres quiz (score du mois) ou rangs XP.",
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def quizlevels(self, ctx: commands.Context) -> None:
        try:
            await _maybe_defer(ctx, ephemeral=False)
            q_lines = [f"**{score}+** pts → {title}" for score, title in core.LEVEL_TITLES_QUIZ]
            g_lines = [f"**Niveau {lvl}+** → {title}" for lvl, title in core.LEVEL_TITLES_GLOBAL]
            em_quiz = discord.Embed(
                title="🎯 Titres quiz (score du mois)",
                description=(
                    "Ton **score** dans **`/quiztop`** augmente quand tu joues aux quiz solo/multi/duel. "
                    "Il est **remis à zéro le 1ᵉʳ de chaque mois** (classement + podium)."
                ),
                color=discord.Color.gold(),
            )
            em_quiz.add_field(
                name="Paliers (points du mois en cours)",
                value="\n".join(q_lines)[:1024],
                inline=False,
            )
            em_quiz.set_footer(text="Menu ci-dessous · Podium : +600 / +350 / +200 XP — /quiztop")
            em_xp = discord.Embed(
                title="🌟 Rangs XP (global)",
                description=(
                    "Ton **niveau** et ta barre d’XP sur **`/profile`** et **`/myrank`** : "
                    "progression **sur toute la durée** (check-in, mini-jeux, quiz…), **sans** reset mensuel."
                ),
                color=discord.Color.purple(),
            )
            em_xp.add_field(
                name="Paliers (niveau)",
                value="\n".join(g_lines)[:1024],
                inline=False,
            )
            em_xp.set_footer(text="Menu ci-dessous pour basculer vers les titres quiz")
            view = QuizLevelsView(ctx.author.id, em_quiz, em_xp)
            msg = await ctx.send(embed=em_quiz, view=view)
            view.message = msg
        except Exception as e:
            logger.error(f"Erreur dans quizlevels: {e}")
            await ctx.send("❌ Une erreur s'est produite.")

    @commands.hybrid_command(name="myrank", description="Affiche ton rang, ton XP et ton titre.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def myrank(self, ctx: commands.Context) -> None:
        try:
            await _maybe_defer(ctx, ephemeral=False)
            levels = core.load_levels()
            scores = core.load_scores()

            user_data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
            quiz_score = scores.get(str(ctx.author.id), 0)

            xp = user_data["xp"]; level = user_data["level"]
            next_xp = core.xp_for_next_level(level)

            embed = discord.Embed(
                title=f"🏅 Rang de {ctx.author.display_name}",
                color=discord.Color.purple()
            )
            progress = core.get_xp_bar(xp, next_xp)
            lg = i18n.ctx_lang(ctx)
            title = core.get_title_for_global_level(level, lg)

            embed.add_field(
                name="📊 Progression",
                value=(
                    f"**Niveau {level}** ({xp}/{next_xp} XP)\n"
                    f"`{progress}`\n"
                    f"Titre actuel : **{title}**"
                ),
                inline=False
            )

            if quiz_score > 0:
                quiz_title = core.get_title_for_quiz_score(quiz_score, lg)
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                position = next((i for i, (uid, _) in enumerate(sorted_scores, 1) if uid == str(ctx.author.id)), None)
                if position is not None:
                    embed.add_field(
                        name="🏆 Classement Quiz",
                        value=(
                            f"Position : **#{position}**\n"
                            f"Score total : **{quiz_score}** points\n"
                            f"Rang quiz : **{quiz_title}**"
                        ),
                        inline=False
                    )

            alu = core.get_linked_username(ctx.author.id)
            if alu:
                embed.add_field(
                    name="🔗 AniList",
                    value=f"Compte lié : **`{alu}`**",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🔗 AniList",
                    value="Non lié — **`/linkanilist`**",
                    inline=False,
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans myrank: {e}")
            await ctx.send("❌ Une erreur s'est produite.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quiz(bot))
