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
from modules.app_cmd_locale import ui_str
from modules import user_reply
from modules import minigame_lock
from modules.core import normalize

logger = logging.getLogger(__name__)


def _human_month(lg: str, year_month: str) -> str:
    """Libellé mois pour podium quiz (FR/EN)."""
    if lg == "en":
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        try:
            y, m = year_month.split("-")
            mi = max(1, min(12, int(m)))
            return f"{months[mi - 1]} {y}"
        except Exception:
            return year_month
    return core.human_month_fr(year_month)


def _embed_footer_anilist_hint(ctx: commands.Context, genres: Optional[List[str]] = None) -> str:
    """Pied d’embed quiz : genres + rappel compte AniList lié ou /linkanilist."""
    lg = i18n.ctx_lang(ctx)
    parts: List[str] = []
    if genres:
        parts.append(i18n.t("quiz.footer_genres", lg, g=", ".join(genres)))
    alu = core.get_linked_username(ctx.author.id)
    if alu:
        parts.append(i18n.t("quiz.footer_al_linked", lg, u=alu))
    else:
        parts.append(i18n.t("quiz.footer_link_hint", lg))
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

    def __init__(self, romaji_title: str, lang: str) -> None:
        super().__init__(timeout=60.0)
        self.romaji_title = romaji_title
        self.lang = lang
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.label = i18n.t("quiz.btn_add_track", lang)[:80]
                break

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

    @discord.ui.button(label="…", style=discord.ButtonStyle.success, emoji="📌", row=0)
    async def add_to_track(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        lg = self.lang
        title = self.romaji_title
        tracker = core.load_tracker()
        uid = str(interaction.user.id)
        lst = tracker.setdefault(uid, [])
        nrm = normalize(title)
        if any(normalize(t) == nrm for t in lst):
            await interaction.response.send_message(
                i18n.t("quiz.track_already", lg),
                ephemeral=True,
            )
            return
        lst.append(title)
        tracker[uid] = lst
        core.save_tracker(tracker)
        await interaction.response.send_message(
            i18n.t("quiz.track_added_ok", lg, title=title),
            ephemeral=True,
        )


async def _send_animequiz_track_offer(ctx: commands.Context, anime: Dict[str, Any]) -> None:
    """Après une manche d’/animequiz, propose d’ajouter l’anime au tracker personnel."""
    romaji = (anime.get("title") or {}).get("romaji")
    if not romaji:
        return
    lg = i18n.ctx_lang(ctx)
    embed = discord.Embed(
        title=i18n.t("quiz.track_offer_title", lg),
        description=i18n.t("quiz.track_offer_desc", lg, romaji=romaji),
        color=discord.Color.teal(),
    )
    cov = (anime.get("coverImage") or {}).get("large") or (anime.get("coverImage") or {}).get("extraLarge")
    if cov:
        embed.set_thumbnail(url=cov)
    embed.set_footer(text=i18n.t("quiz.track_offer_footer", lg))
    try:
        view = AnimequizTrackOfferView(romaji, lg)
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
    def __init__(self, challenger: discord.Member, opponent: discord.Member, *, lang: str, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.challenger = challenger
        self.opponent = opponent
        self.lang = lang
        self.accepted: Optional[bool] = None
        self.message: Optional[discord.Message] = None
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.style == discord.ButtonStyle.success:
                    child.label = i18n.t("quiz.btn_accept", lang)[:80]
                elif child.style == discord.ButtonStyle.danger:
                    child.label = i18n.t("quiz.btn_decline", lang)[:80]

    async def on_timeout(self):
        if self.message and self.accepted is None:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            try:
                await self.message.edit(content=i18n.t("quiz.invite_expired", self.lang), view=self)
            except Exception:
                pass

    async def _only_opponent(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message(i18n.t("quiz.duel_only_opponent", self.lang), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="…", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._only_opponent(interaction):
            return
        self.accepted = True
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(
            content=i18n.t("quiz.duel_accept_edit", self.lang, name=self.opponent.display_name),
            view=self,
        )
        self.stop()

    @discord.ui.button(label="…", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._only_opponent(interaction):
            return
        self.accepted = False
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(
            content=i18n.t("quiz.duel_decline_edit", self.lang, name=self.opponent.display_name),
            view=self,
        )
        self.stop()


class QuizLevelsSelect(discord.ui.Select):
    """Menu : titres quiz (score du mois) ou rangs XP globaux (/profile)."""

    def __init__(self, lang: str) -> None:
        super().__init__(
            placeholder=i18n.t("quiz.levels_ph", lang)[:150],
            options=[
                discord.SelectOption(
                    label=i18n.t("quiz.levels_opt_quiz", lang)[:100],
                    value="quiz",
                    emoji="🎯",
                    default=True,
                ),
                discord.SelectOption(
                    label=i18n.t("quiz.levels_opt_xp", lang)[:100],
                    value="xp",
                    emoji="🌟",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.view
        if not isinstance(parent, QuizLevelsView):
            lg = i18n.interaction_lang(interaction)
            await interaction.response.send_message(
                i18n.t("quiz.levels_expired", lg),
                ephemeral=True,
            )
            return
        key = (self.values[0] if self.values else "quiz") or "quiz"
        emb = parent._quiz_embed if key == "quiz" else parent._xp_embed
        await interaction.response.edit_message(embed=emb, view=parent)


class QuizLevelsView(discord.ui.View):
    def __init__(self, author_id: int, quiz_embed: discord.Embed, xp_embed: discord.Embed, lang: str) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.lang = lang
        self._quiz_embed = quiz_embed
        self._xp_embed = xp_embed
        self.add_item(QuizLevelsSelect(lang))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            lg = i18n.interaction_lang(interaction)
            await interaction.response.send_message(i18n.t("quiz.menu_not_yours", lg), ephemeral=True)
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

    @commands.hybrid_command(name="animequiz", description=ui_str("slash.quiz_animequiz"))
    @commands.cooldown(1, 15, commands.BucketType.user)
    @app_commands.describe(difficulty=ui_str("slash.quiz_param_difficulty"))
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name=ui_str("slash.choice_quiz_easy"), value="easy"),
            app_commands.Choice(name=ui_str("slash.choice_quiz_medium"), value="medium"),
            app_commands.Choice(name=ui_str("slash.choice_quiz_hard"), value="hard"),
        ]
    )
    async def animequiz(self, ctx: commands.Context, difficulty: str = "medium") -> None:
        uid = ctx.author.id
        lg = i18n.ctx_lang(ctx)
        await _maybe_defer(ctx)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "animequiz"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            await ctx.send(i18n.t("quiz.animequiz_prep", lg))

            sort_option = SORT_BY_DIFF.get((difficulty or "medium").lower(), "SCORE_DESC")

            anime = await self._fetch_random_anilist_media(sort_option, queue_ctx=ctx)
            if not anime:
                await ctx.send(core.anilist_error_user_message())
                return

            correct_titles = self._titles_set(anime)

            embed = discord.Embed(
                title=i18n.t("quiz.animequiz_embed_title", lg),
                description=i18n.t("quiz.animequiz_embed_desc", lg),
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
                    await ctx.send(i18n.t("quiz.pass_header", lg) + "\n".join(lines))
                    await _send_animequiz_track_offer(ctx, anime)
                    return

                if self.title_matcher.find_matches(guess, correct_titles):
                    await ctx.send(i18n.t("quiz.correct_solo", lg, name=ctx.author.display_name))

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
                        await ctx.send(i18n.t("quiz.other_titles", lg, titles=", ".join(other_titles)))
                    await _send_animequiz_track_offer(ctx, anime)
                else:
                    await ctx.send(i18n.t("quiz.wrong_solo", lg, title=anime["title"].get("romaji")))
                    await _send_animequiz_track_offer(ctx, anime)

            except asyncio.TimeoutError:
                await ctx.send(i18n.t("quiz.timeout_solo", lg, title=anime["title"].get("romaji")))
                await _send_animequiz_track_offer(ctx, anime)

        except Exception as e:
            logger.error(f"Erreur dans animequiz: {e}")
            await ctx.send(i18n.t("quiz.error_animequiz", lg))
        finally:
            minigame_lock.end(uid)

    @commands.hybrid_command(name="animequizmulti", description=ui_str("slash.quiz_animequizmulti"))
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(nb_questions=ui_str("slash.quiz_param_nb_questions"))
    async def animequizmulti(
        self,
        ctx: commands.Context,
        nb_questions: app_commands.Range[int, 5, 20] = 5,
    ) -> None:
        uid = ctx.author.id
        lg = i18n.ctx_lang(ctx)
        await _maybe_defer(ctx)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "animequizmulti"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            if not 5 <= nb_questions <= 20:
                await ctx.send(i18n.t("quiz.multi_bad_range", lg))
                return

            await ctx.send(i18n.t("quiz.multi_launch", lg, n=nb_questions))
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
                        title=i18n.t(
                            "quiz.multi_q_title",
                            lg,
                            i=i + 1,
                            total=nb_questions,
                            diff=difficulty,
                        ),
                        description=i18n.t("quiz.multi_q_desc", lg),
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
                            await ctx.send(i18n.t("quiz.multi_pass", lg, title=anime["title"].get("romaji")))
                            combo = 0
                        else:
                            if self.title_matcher.find_matches(guess, correct_titles):
                                tshow = core.format_anilist_title_obj(anime.get("title"))
                                await ctx.send(i18n.t("quiz.multi_correct", lg, title=tshow))
                                score += 1
                                xp_gain = 5 if difficulty == "easy" else 10 if difficulty == "medium" else 15
                                total_xp += xp_gain
                                core.add_mini_score(ctx.author.id, "animequiz", 1)
                                combo += 1
                                if combo == 3:
                                    combo_bonus_total += 2
                                    await ctx.send(i18n.t("quiz.combo3", lg))
                                elif combo == 5:
                                    combo_bonus_total += 5
                                    await ctx.send(i18n.t("quiz.combo5", lg))
                            else:
                                await ctx.send(i18n.t("quiz.multi_wrong", lg, title=anime["title"].get("romaji")))
                                combo = 0

                    except asyncio.TimeoutError:
                        await ctx.send(i18n.t("quiz.multi_timeout", lg, title=anime["title"].get("romaji")))
                        combo = 0

                except Exception as e:
                    logger.error(f"Erreur question {i + 1}: {e}")
                    continue

                await asyncio.sleep(1.2)

            if rounds_with_anime == 0:
                await ctx.send(i18n.t("quiz.multi_no_load", lg))
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
                await ctx.send(i18n.t("quiz.multi_penalty", lg, n=penalty))
            await core.announce_quiz_title_if_changed(self.bot, ctx.channel, ctx.author.id, old_q, new_q)

            total_xp += combo_bonus_total
            if total_xp > 0:
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, total_xp)

            precision = (score / rounds_with_anime * 100) if rounds_with_anime > 0 else 0.0
            # Mission: win multi si ≥ 50%
            if score >= max(1, rounds_with_anime // 2):
                self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_win")

            embed = discord.Embed(
                title=i18n.t("quiz.multi_done_title", lg),
                description=i18n.t(
                    "quiz.multi_done_desc",
                    lg,
                    score=score,
                    played=rounds_with_anime,
                    planned=nb_questions,
                    xp=total_xp,
                    combo=combo_bonus_total,
                    pct=precision,
                ),
                color=discord.Color.gold(),
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans animequizmulti: {e}")
            await ctx.send(i18n.t("quiz.error_multi", lg))
        finally:
            minigame_lock.end(uid)

    # ---------- DUEL AMÉLIORÉ ----------
    @commands.hybrid_command(
        name="duel",
        description=ui_str("slash.quiz_duel"),
    )
    @app_commands.rename(
        opponent=ui_str("slash.param_duel_opponent"),
        manches=ui_str("slash.param_duel_manches"),
        difficulte=ui_str("slash.param_duel_difficulte"),
    )
    @app_commands.describe(
        opponent=ui_str("slash.quiz_duel_opponent"),
        manches=ui_str("slash.quiz_duel_manches"),
        difficulte=ui_str("slash.quiz_duel_difficulte"),
    )
    @app_commands.choices(
        manches=[app_commands.Choice(name=str(i), value=i) for i in range(1, 11)],
        difficulte=[
            app_commands.Choice(name=ui_str("slash.choice_quiz_easy"), value="easy"),
            app_commands.Choice(name=ui_str("slash.choice_quiz_medium"), value="medium"),
            app_commands.Choice(name=ui_str("slash.choice_quiz_hard"), value="hard"),
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
        lg = i18n.ctx_lang(ctx)
        try:
            await _maybe_defer(ctx)
            if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
                return

            # Garde-fous
            if opponent.bot:
                await ctx.send(i18n.t("quiz.duel_bot", lg))
                return
            if opponent.id == ctx.author.id:
                await ctx.send(i18n.t("quiz.duel_self", lg))
                return

            for uid in (ctx.author.id, opponent.id):
                left = _duel_cooldown_remaining(uid)
                if left > 0:
                    await user_reply.send_ephemeral_or_private(
                        ctx,
                        i18n.t("quiz.duel_cooldown", lg, s=int(left) + 1),
                    )
                    return
    
            manches = max(1, min(int(manches), 10))
            diff = (difficulte or "medium").lower()
            sort_option = SORT_BY_DIFF.get(diff, "SCORE_DESC")
    
            # Verrou par salon
            channel_id = ctx.channel.id
            if _active_duels_per_channel.get(channel_id):
                await ctx.send(i18n.t("quiz.duel_channel_busy", lg))
                return
            _active_duels_per_channel[channel_id] = True
    
            # Invitation
            invite_view = DuelInviteView(challenger=ctx.author, opponent=opponent, lang=lg, timeout=45)
            msg = await ctx.send(
                content=i18n.t(
                    "quiz.duel_invite",
                    lg,
                    ch=ctx.author.mention,
                    op=opponent.mention,
                    m=manches,
                    d=diff,
                ),
                view=invite_view
            )
            invite_view.message = msg
    
            await invite_view.wait()
            if invite_view.accepted is not True:
                if invite_view.accepted is None:
                    await ctx.send(i18n.t("quiz.duel_no_answer", lg))
                return

            duel_started = True
    
            # OK duel
            players = (ctx.author, opponent)
            scores = {ctx.author.id: 0, opponent.id: 0}
    
            await ctx.send(
                i18n.t(
                    "quiz.duel_rules",
                    lg,
                    p1=players[0].display_name,
                    p2=players[1].display_name,
                    m=manches,
                    ignored=", ".join(sorted(IGNORED_ANSWERS)),
                )
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
                    title=i18n.t("quiz.duel_round_title", lg, i=i, m=manches),
                    description=i18n.t("quiz.duel_round_desc", lg, timeout=ANSWER_TIMEOUT),
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
                            await ctx.send(i18n.t("quiz.duel_jsp", lg, mention=msg.author.mention))
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
                        i18n.t(
                            "quiz.duel_point",
                            lg,
                            winner=winner.display_name,
                            reveal=reveal,
                            p1=players[0].display_name,
                            s1=scores[players[0].id],
                            s2=scores[players[1].id],
                            p2=players[1].display_name,
                        )
                    )
                    try:
                        await core.add_xp(self.bot, ctx.channel, winner.id, 6)
                        core.add_mini_score(winner.id, "duel", 1)
                    except Exception:
                        pass
                else:
                    # Timeout OU double "jsp" ⇒ on révèle
                    if jsp_flags[players[0].id] and jsp_flags[players[1].id]:
                        await ctx.send(
                            i18n.t(
                                "quiz.duel_double_pass",
                                lg,
                                reveal=reveal,
                                p1=players[0].display_name,
                                s1=scores[players[0].id],
                                s2=scores[players[1].id],
                                p2=players[1].display_name,
                            )
                        )
                    else:
                        await ctx.send(
                            i18n.t(
                                "quiz.duel_timeout_reveal",
                                lg,
                                reveal=reveal,
                                p1=players[0].display_name,
                                s1=scores[players[0].id],
                                s2=scores[players[1].id],
                                p2=players[1].display_name,
                            )
                        )
    
                await asyncio.sleep(1)
    
            s1, s2 = scores[players[0].id], scores[players[1].id]
            champ = players[0] if s1 > s2 else players[1] if s2 > s1 else None
    
            if champ:
                embed = discord.Embed(
                    title=i18n.t("quiz.duel_final_win", lg),
                    description=i18n.t(
                        "quiz.duel_final_win_desc",
                        lg,
                        champ=champ.display_name,
                        p1=players[0].display_name,
                        s1=s1,
                        s2=s2,
                        p2=players[1].display_name,
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
                    title=i18n.t("quiz.duel_final_draw_title", lg),
                    description=i18n.t(
                        "quiz.duel_final_draw_desc",
                        lg,
                        p1=players[0].display_name,
                        s1=s1,
                        s2=s2,
                        p2=players[1].display_name,
                    ),
                    color=discord.Color.gold()
                ))
    
        except Exception as e:
            logger.error(f"Erreur dans duel: {e}")
            await ctx.send(i18n.t("quiz.error_duel", lg))
        finally:
            _active_duels_per_channel.pop(ctx.channel.id, None)
            if duel_started:
                _mark_duel_ended(ctx.author.id, opponent.id)


    @commands.hybrid_command(name="quiztop", description=ui_str("slash.quiz_quiztop"))
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def quiztop(self, ctx: commands.Context) -> None:
        lg = i18n.ctx_lang(ctx)
        try:
            await _maybe_defer(ctx, ephemeral=False)

            # Top du mois en cours
            scores = core.load_scores()  # {user_id_str: score_int}
            top10 = core.compute_quiz_top(scores, n=10)  # [(uid_str, score_int), ...]

            em = discord.Embed(
                title=i18n.t("quiz.quiztop_title", lg),
                color=discord.Color.gold()
            )

            if not top10:
                em.description = i18n.t("quiz.quiztop_empty", lg)
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
                    lines.append(i18n.t("quiz.quiztop_line", lg, badge=badge, display=display, sc=sc))
                em.add_field(name=i18n.t("quiz.quiztop_field_top", lg), value="\n".join(lines)[:1024], inline=False)

            # Mois dernier (écrit par quiz_reset) : podium + récompenses XP/badges envoyées en MP
            w = core.load_winner()
            if w and w.get("month"):
                label = _human_month(lg, w["month"])
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
                        lines_p.append(i18n.t("quiz.quiztop_line", lg, badge=md, display=disp, sc=sc))
                    if lines_p:
                        em.add_field(
                            name=i18n.t("quiz.quiztop_podium", lg, month=label),
                            value="\n".join(lines_p)[:1024],
                            inline=False,
                        )
                        em.add_field(
                            name=i18n.t("quiz.quiztop_rewards_name", lg),
                            value=i18n.t("quiz.quiztop_rewards_val", lg),
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
                        em.add_field(
                            name=i18n.t("quiz.quiztop_winner", lg, month=label),
                            value=i18n.t("quiz.quiztop_winner_line", lg, name=wname, sc=wsc),
                            inline=False,
                        )
                    else:
                        em.add_field(
                            name=i18n.t("quiz.quiztop_winner", lg, month=label),
                            value=i18n.t("quiz.quiztop_no_winner", lg),
                            inline=False,
                        )

            # Compte à rebours vers le prochain reset (1er du mois 00:00)
            tz = getattr(core, "TIMEZONE", timezone.utc)
            nxt = _next_reset_dt(tz)
            left = _human_td(nxt - datetime.now(tz))
            ft = i18n.t("quiz.quiztop_footer", lg, date=f"{nxt:%d/%m %H:%M}", left=left)
            alu = core.get_linked_username(ctx.author.id)
            if alu:
                ft += i18n.t("quiz.quiztop_footer_al", lg, alu=alu)
            else:
                ft += i18n.t("quiz.quiztop_footer_nolink", lg)
            em.set_footer(text=ft[:2048])

            await ctx.send(embed=em)

        except Exception as e:
            logger.error(f"Erreur dans quiztop: {e}")
            await ctx.send(i18n.t("quiz.error_generic", lg))

    @commands.hybrid_command(
        name="quizlevels",
        description=ui_str("slash.quiz_quizlevels"),
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def quizlevels(self, ctx: commands.Context) -> None:
        lg = i18n.ctx_lang(ctx)
        try:
            await _maybe_defer(ctx, ephemeral=False)
            q_lines = [f"**{score}+** pts → {title}" for score, title in core.LEVEL_TITLES_QUIZ]
            g_lines = [f"**Niveau {lvl}+** → {title}" for lvl, title in core.LEVEL_TITLES_GLOBAL]
            em_quiz = discord.Embed(
                title=i18n.t("quiz.levels_quiz_title", lg),
                description=i18n.t("quiz.levels_quiz_desc", lg),
                color=discord.Color.gold(),
            )
            em_quiz.add_field(
                name=i18n.t("quiz.levels_quiz_field", lg),
                value="\n".join(q_lines)[:1024],
                inline=False,
            )
            em_quiz.set_footer(text=i18n.t("quiz.levels_quiz_footer", lg))
            em_xp = discord.Embed(
                title=i18n.t("quiz.levels_xp_title", lg),
                description=i18n.t("quiz.levels_xp_desc", lg),
                color=discord.Color.purple(),
            )
            em_xp.add_field(
                name=i18n.t("quiz.levels_xp_field", lg),
                value="\n".join(g_lines)[:1024],
                inline=False,
            )
            em_xp.set_footer(text=i18n.t("quiz.levels_xp_footer", lg))
            view = QuizLevelsView(ctx.author.id, em_quiz, em_xp, lg)
            msg = await ctx.send(embed=em_quiz, view=view)
            view.message = msg
        except Exception as e:
            logger.error(f"Erreur dans quizlevels: {e}")
            await ctx.send(i18n.t("quiz.error_generic", lg))

    @commands.hybrid_command(name="myrank", description=ui_str("slash.quiz_myrank"))
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def myrank(self, ctx: commands.Context) -> None:
        lg = i18n.ctx_lang(ctx)
        try:
            await _maybe_defer(ctx, ephemeral=False)
            levels = core.load_levels()
            scores = core.load_scores()

            user_data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
            quiz_score = scores.get(str(ctx.author.id), 0)

            xp = user_data["xp"]; level = user_data["level"]
            next_xp = core.xp_for_next_level(level)

            embed = discord.Embed(
                title=i18n.t("quiz.myrank_title", lg, name=ctx.author.display_name),
                color=discord.Color.purple()
            )
            progress = core.get_xp_bar(xp, next_xp)
            title = core.get_title_for_global_level(level, lg)

            embed.add_field(
                name=i18n.t("quiz.myrank_progress_name", lg),
                value=i18n.t(
                    "quiz.myrank_progress_val",
                    lg,
                    level=level,
                    xp=xp,
                    next_xp=next_xp,
                    bar=progress,
                    title=title,
                ),
                inline=False
            )

            if quiz_score > 0:
                quiz_title = core.get_title_for_quiz_score(quiz_score, lg)
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                position = next((i for i, (uid, _) in enumerate(sorted_scores, 1) if uid == str(ctx.author.id)), None)
                if position is not None:
                    embed.add_field(
                        name=i18n.t("quiz.myrank_quiz_name", lg),
                        value=i18n.t(
                            "quiz.myrank_quiz_val",
                            lg,
                            pos=position,
                            score=quiz_score,
                            qtitle=quiz_title,
                        ),
                        inline=False
                    )

            alu = core.get_linked_username(ctx.author.id)
            if alu:
                embed.add_field(
                    name=i18n.t("quiz.myrank_al_name", lg),
                    value=i18n.t("quiz.myrank_al_linked", lg, name=alu),
                    inline=False,
                )
            else:
                embed.add_field(
                    name=i18n.t("quiz.myrank_al_name", lg),
                    value=i18n.t("quiz.myrank_al_unlinked", lg),
                    inline=False,
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans myrank: {e}")
            await ctx.send(i18n.t("quiz.error_generic", lg))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quiz(bot))
