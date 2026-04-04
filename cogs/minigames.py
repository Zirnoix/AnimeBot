"""
Mini-games commands.

* `/minijeux` — deux menus : **Devinettes (Guess)** et **Autres** (lance la partie ; duel → /duel)
* `/higherlower` — popularité
* Raccourcis slash : `/guessyear`, `/guessepisodes`, `/guessgenre`, `/guesscharacter` (même logique que le menu).
"""

from __future__ import annotations
import logging
import time
from collections import deque
from typing import Any
import random
import asyncio
import discord
from discord.ext import commands
from discord.ui import View, Button, Select
from modules import anilist_gate
from modules import core
from modules import higherlower_combine
from modules import i18n
from modules.app_cmd_locale import ui_str
from modules import minigame_lock

LOG = logging.getLogger(__name__)


def _mission_guess_win(bot: commands.Bot, user_id: int) -> None:
    """Progression mission HARD « guess_win » (défini dans mission_definitions)."""
    try:
        bot.dispatch("mission_progress", user_id, "_custom:guess_win")
    except Exception:
        pass


class _FakeAuthor:
    __slots__ = ("id",)

    def __init__(self, uid: int) -> None:
        self.id = uid


class _FakeMessage:
    __slots__ = ("author",)

    def __init__(self, uid: int) -> None:
        self.author = _FakeAuthor(uid)


def _hybrid_cmd_cooldown_retry(command: commands.Command | None, user_id: int) -> float:
    """Retry-after (s) pour un hybrid command avec BucketType.user, ou 0 si dispo."""
    if command is None:
        return 0.0
    inner = getattr(command, "_command", command)
    if not getattr(inner, "_buckets", None):
        return 0.0
    now = time.time()
    fake = _FakeMessage(user_id)
    bucket = inner._buckets.get_bucket(fake, current=now)
    if bucket is None:
        return 0.0
    return max(0.0, float(bucket.get_retry_after(current=now)))


def _hybrid_cmd_cooldown_touch(command: commands.Command | None, user_id: int) -> None:
    """Consomme un créneau cooldown (comme au lancement slash d’une commande)."""
    if command is None:
        return
    inner = getattr(command, "_command", command)
    if not getattr(inner, "_buckets", None):
        return
    now = time.time()
    fake = _FakeMessage(user_id)
    bucket = inner._buckets.get_bucket(fake, current=now)
    if bucket is None:
        return
    bucket.update_rate_limit(now)


# Map menu minijeux → nom de commande bot (get_command)
_MENU_MINI_CMD: dict[str, str] = {
    "higherlower": "higherlower",
    "guess_year": "guessyear",
    "guess_episodes": "guessepisodes",
    "guess_genre": "guessgenre",
    "guess_character": "guesscharacter",
    "guessop": "guessop",
    "animequiz": "animequiz",
    "animequizmulti": "animequizmulti",
    "chainquiz": "chainquiz",
    "guesswho": "guesswho",
}


# --- Anti-spam /guess genre (réponses « faciles » trop souvent gagnantes) ---
_SPAM_GENRE_NAMES = frozenset({
    "action", "adventure", "comedy", "drama", "fantasy", "romance",
    "sci-fi", "sci fi", "slice of life", "mystery", "supernatural", "thriller",
    "horror", "psychological", "school", "sports", "music", "mecha",
    "ecchi", "shounen", "shoujo", "seinen", "josei",
})
_GUESS_GENRE_SPAM_STREAK: dict[int, int] = {}
_GUESS_GENRE_SPAM_TIMES: dict[int, deque[float]] = {}
_GUESS_GENRE_COOLDOWN_UNTIL: dict[int, float] = {}
_GUESS_GENRE_COOLDOWN_SEC = 120.0  # base (si pas de strikes)
_SPAM_WINDOW_SEC = 300.0
_SPAM_MAX_STREAK = 3  # au-delà : 4e victoire « facile » d’affilée → pénalité
_SPAM_MAX_IN_WINDOW = 3  # au-delà : 4e en 5 min → pénalité
# Même genre « facile » répété dans la fenêtre (compteur par mot normalisé)
_ATTEMPT_SOFT_WARN = 2  # 1er avertissement salon (avant sanction)
_ATTEMPT_HARD_WARN = 3  # dernier avertissement explicite
_ATTEMPT_PENALTY = 4  # sanction (−XP + cooldown progressif)

_GUESS_GENRE_SPAM_ATTEMPTS: dict[int, deque[tuple[float, str]]] = {}
# Sanctions progressives : ne se remet pas à zéro juste après un cooldown
_GUESS_GENRE_STRIKES: dict[int, int] = {}


def _guess_genre_is_spam_candidate(guess: str) -> bool:
    g = (guess or "").strip().lower()
    if g in _SPAM_GENRE_NAMES:
        return True
    g2 = g.replace("-", " ").strip()
    return g2 in _SPAM_GENRE_NAMES


def _guess_genre_prune_times(uid: int, now: float) -> deque[float]:
    dq = _GUESS_GENRE_SPAM_TIMES.setdefault(uid, deque(maxlen=32))
    while dq and now - dq[0] > _SPAM_WINDOW_SEC:
        dq.popleft()
    return dq


def _easy_genre_hint_short(lg: str) -> str:
    names = sorted(_SPAM_GENRE_NAMES, key=lambda s: s.lower())
    sample = ", ".join(n.replace("-", " ").title() for n in names[:14])
    return i18n.t("minigames.gg_hint_line", lg, sample=sample)


def _guess_genre_norm_key(guess: str) -> str:
    g = (guess or "").strip().lower().replace("-", " ")
    while "  " in g:
        g = g.replace("  ", " ")
    return g.strip()


def _guess_genre_prune_attempt_dq(uid: int, now: float) -> deque[tuple[float, str]]:
    dq = _GUESS_GENRE_SPAM_ATTEMPTS.setdefault(uid, deque(maxlen=32))
    while dq and now - dq[0][0] > _SPAM_WINDOW_SEC:
        dq.popleft()
    return dq


def _clear_guess_genre_spam(uid: int) -> None:
    """Reset complet (timeout, mauvaise réponse qui casse la série)."""
    _GUESS_GENRE_SPAM_STREAK.pop(uid, None)
    _GUESS_GENRE_SPAM_TIMES.pop(uid, None)
    _GUESS_GENRE_SPAM_ATTEMPTS.pop(uid, None)


def _clear_guess_genre_streak_only(uid: int) -> None:
    """Garde l’historique des tentatives « même genre » (anti re-spam après sanction)."""
    _GUESS_GENRE_SPAM_STREAK.pop(uid, None)
    _GUESS_GENRE_SPAM_TIMES.pop(uid, None)


def _remove_attempt_key(uid: int, key: str) -> None:
    """Retire une clé du deque après sanction pour ce mot (évite double sanction instantanée)."""
    dq = _GUESS_GENRE_SPAM_ATTEMPTS.get(uid)
    if not dq:
        return
    _GUESS_GENRE_SPAM_ATTEMPTS[uid] = deque([(t, k) for t, k in dq if k != key], maxlen=32)


def _genre_strike_cooldown_sec(uid: int) -> float:
    s = _GUESS_GENRE_STRIKES.get(uid, 0)
    return min(900.0, 90.0 + s * 75.0)


def _genre_strike_xp(uid: int) -> int:
    """1re sanction : −5 XP, puis −8, −11… (progressif)."""
    s = _GUESS_GENRE_STRIKES.get(uid, 0)
    return -(5 + min(max(s - 1, 0), 5) * 3)


class MiniGamesInteractionContext:
    """Contexte minimal pour lancer des mini-jeux depuis un Select (pas de `command` data slash)."""

    __slots__ = ("bot", "interaction", "channel", "guild", "author", "prefix", "invoked_with")

    def __init__(self, bot: commands.Bot, interaction: discord.Interaction) -> None:
        self.bot = bot
        self.interaction = interaction
        self.channel = interaction.channel
        self.guild = interaction.guild
        author = interaction.user
        if interaction.guild is not None:
            m = interaction.guild.get_member(author.id)
            if m is not None:
                author = m
        self.author = author
        self.prefix = "!"
        self.invoked_with = None

    async def send(self, *args: Any, **kwargs: Any) -> discord.Message:
        return await self.interaction.followup.send(*args, **kwargs)


class HigherLowerView(View):
    def __init__(self, ctx, choice1, choice2):
        super().__init__(timeout=20)
        self.ctx = ctx
        self.lang = i18n.ctx_lang(ctx)
        self.choice1 = choice1
        self.choice2 = choice2
        self.result_sent = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(i18n.t("minigames.hl_not_yours", self.lang), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="1️⃣", style=discord.ButtonStyle.primary)
    async def button_1(self, interaction: discord.Interaction, button: Button):
        await self.resolve(interaction, "1")

    @discord.ui.button(label="2️⃣", style=discord.ButtonStyle.success)
    async def button_2(self, interaction: discord.Interaction, button: Button):
        await self.resolve(interaction, "2")

    async def resolve(self, interaction: discord.Interaction, answer: str):
        if self.result_sent:
            return
        self.result_sent = True

        pop1 = self.choice1.get("popularity", 0)
        pop2 = self.choice2.get("popularity", 0)
        correct = "1" if pop1 >= pop2 else "2"

        lg = self.lang
        t1 = self.choice1["title"]["romaji"]
        t2 = self.choice2["title"]["romaji"]
        if answer == correct:
            await interaction.response.send_message(
                i18n.t("minigames.hl_win", lg, t1=t1, p1=pop1, t2=t2, p2=pop2)
            )
            await core.add_xp(interaction.client, interaction.channel, interaction.user.id, 5)
            core.add_mini_score(interaction.user.id, "higherlower", 1)
        else:
            await interaction.response.send_message(
                i18n.t("minigames.hl_lose", lg, t1=t1, p1=pop1, t2=t2, p2=pop2)
            )
        self.stop()


class MinijeuxGuessSelect(Select):
    """Menu déroulant : tous les modes Guess (+ Guess OP)."""

    def __init__(self, lang: str) -> None:
        super().__init__(
            custom_id="minijeux_guess_pick",
            placeholder=i18n.t("minigames.guess_ph", lang)[:150],
            options=[
                discord.SelectOption(
                    label=i18n.t("minigames.guess_year_l", lang)[:100],
                    value="guess_year",
                    description=i18n.t("minigames.guess_year_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.guess_ep_l", lang)[:100],
                    value="guess_episodes",
                    description=i18n.t("minigames.guess_ep_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.guess_genre_l", lang)[:100],
                    value="guess_genre",
                    description=i18n.t("minigames.guess_genre_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.guess_char_l", lang)[:100],
                    value="guess_character",
                    description=i18n.t("minigames.guess_char_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.guessop_l", lang)[:100],
                    value="guessop",
                    description=i18n.t("minigames.guessop_d", lang)[:100],
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        hub = self.view
        if not isinstance(hub, MinijeuxHubView):
            LOG.error("MinijeuxGuessSelect: view inattendue %r", type(hub))
            return
        if interaction.user.id != hub.invoker_id:
            await interaction.response.send_message(
                i18n.t("minigames.hub_not_yours", i18n.interaction_lang(interaction)),
                ephemeral=True,
            )
            return
        key = self.values[0] if self.values else ""
        await hub.cog._run_minigame_choice(interaction, key)


class MinijeuxAutresSelect(Select):
    """Menu déroulant : quiz, higher/lower, duel (rappel)."""

    def __init__(self, lang: str) -> None:
        super().__init__(
            custom_id="minijeux_autres_pick",
            placeholder=i18n.t("minigames.autres_ph", lang)[:150],
            options=[
                discord.SelectOption(
                    label=i18n.t("minigames.hl_menu_l", lang)[:100],
                    value="higherlower",
                    description=i18n.t("minigames.hl_menu_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.aq_solo_l", lang)[:100],
                    value="animequiz",
                    description=i18n.t("minigames.aq_solo_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.aq_multi_l", lang)[:100],
                    value="animequizmulti",
                    description=i18n.t("minigames.aq_multi_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.duel_menu_l", lang)[:100],
                    value="duel",
                    description=i18n.t("minigames.duel_menu_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.chain_l", lang)[:100],
                    value="chainquiz",
                    description=i18n.t("minigames.chain_d", lang)[:100],
                ),
                discord.SelectOption(
                    label=i18n.t("minigames.gw_l", lang)[:100],
                    value="guesswho",
                    description=i18n.t("minigames.gw_d", lang)[:100],
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        hub = self.view
        if not isinstance(hub, MinijeuxHubView):
            LOG.error("MinijeuxAutresSelect: view inattendue %r", type(hub))
            return
        if interaction.user.id != hub.invoker_id:
            await interaction.response.send_message(
                i18n.t("minigames.hub_not_yours", i18n.interaction_lang(interaction)),
                ephemeral=True,
            )
            return
        key = self.values[0] if self.values else ""
        await hub.cog._run_minigame_choice(interaction, key)


class MinijeuxHubView(View):
    """Deux menus : Guess (devinettes) et Autres (quiz, H/L, rappel duel)."""

    def __init__(self, cog: "MiniGames", invoker_id: int, lang: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.invoker_id = invoker_id
        self.lang = lang
        self.add_item(MinijeuxGuessSelect(lang))
        self.add_item(MinijeuxAutresSelect(lang))


class MiniGames(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _run_minigame_choice(self, interaction: discord.Interaction, key: str) -> None:
        """Lance un mini-jeu depuis un menu (Select) : même logique que les commandes slash."""
        lg = i18n.interaction_lang(interaction)
        if not await anilist_gate.ensure_anilist_for_interaction(self.bot, interaction):
            return
        await interaction.response.defer(thinking=True)
        uid = interaction.user.id
        cmd_name = _MENU_MINI_CMD.get(key)
        if cmd_name:
            sub = self.bot.get_command(cmd_name)
            ra = _hybrid_cmd_cooldown_retry(sub, uid)
            if ra > 0:
                try:
                    await interaction.followup.send(
                        i18n.t("minigames.cooldown", lg, s=int(ra) + 1),
                        ephemeral=True,
                    )
                except Exception:
                    pass
                return
            _hybrid_cmd_cooldown_touch(sub, uid)
        # Retire le message « choisis un mini-jeu » pour ne pas encombrer le salon
        try:
            msg = interaction.message
            if msg is not None:
                await msg.delete()
        except (discord.HTTPException, discord.NotFound):
            pass
        ctx: commands.Context = MiniGamesInteractionContext(self.bot, interaction)  # type: ignore[assignment]
        try:
            if key == "duel":
                await interaction.followup.send(
                    i18n.t("minigames.duel_slash", lg),
                    ephemeral=True,
                )
                return
            if key == "higherlower":
                await self.higher_lower(ctx)
            elif key == "guess_year":
                await self._guess_year(ctx)
            elif key == "guess_episodes":
                await self._guess_episodes(ctx)
            elif key == "guess_genre":
                await self._guess_genre(ctx)
            elif key == "guess_character":
                await self._guess_character(ctx)
            elif key == "guessop":
                og = self.bot.get_cog("Openings")
                if og:
                    await og.guess_op(ctx)  # type: ignore[attr-defined]
                else:
                    await interaction.followup.send(i18n.t("minigames.no_guessop", lg), ephemeral=True)
            elif key == "animequiz":
                qz = self.bot.get_cog("Quiz")
                if qz:
                    await qz.animequiz(ctx, "medium")  # type: ignore[attr-defined]
                else:
                    await interaction.followup.send(i18n.t("minigames.no_quiz", lg), ephemeral=True)
            elif key == "animequizmulti":
                qz = self.bot.get_cog("Quiz")
                if qz:
                    await qz.animequizmulti(ctx, 5)  # type: ignore[attr-defined]
                else:
                    await interaction.followup.send(i18n.t("minigames.no_quiz", lg), ephemeral=True)
            elif key in {"chainquiz", "guesswho"}:
                cg = self.bot.get_cog("CommunityGames")
                if cg:
                    if key == "chainquiz":
                        await cg.chainquiz(ctx)  # type: ignore[attr-defined]
                    else:
                        await cg.guesswho(ctx)  # type: ignore[attr-defined]
                else:
                    await interaction.followup.send(i18n.t("minigames.no_minigame", lg), ephemeral=True)
            else:
                await interaction.followup.send(i18n.t("minigames.unknown_option", lg), ephemeral=True)
        except Exception:
            LOG.exception("minigame dispatch failed (%s)", key)
            try:
                await interaction.followup.send(
                    i18n.t("minigames.dispatch_err", lg),
                    ephemeral=True,
                )
            except Exception:
                pass

    # --------------------------------------
    # Guess (year, episodes, genre, character) — /guess* + /minijeux
    # --------------------------------------
    @commands.hybrid_command(name="higherlower", description=ui_str("slash.minigames_higherlower"))
    @commands.cooldown(1, 18, commands.BucketType.user)
    async def higher_lower(self, ctx: commands.Context):
        uid = ctx.author.id
        lg = i18n.ctx_lang(ctx)
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "higherlower"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            await ctx.send(i18n.t("minigames.hl_prep", lg))

            page = random.randint(1, 10)
            query = '''
            query ($page: Int) {
              Page(page: $page, perPage: 50) {
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                  title { romaji }
                  popularity
                  coverImage { extraLarge }
                }
              }
            }
            '''
            data = await core.query_anilist_async(query, {"page": page}, queue_ctx=ctx)
            if not data or not data.get("data"):
                await ctx.send(core.anilist_error_user_message())
                return

            media_list = data["data"]["Page"]["media"]
            if len(media_list) < 2:
                await ctx.send(i18n.t("minigames.not_enough_data", lg))
                return

            choice1, choice2 = random.sample(media_list, 2)

            embed = discord.Embed(
                title=i18n.t("minigames.hl_title", lg),
                description=i18n.t(
                    "minigames.hl_desc",
                    lg,
                    t1=choice1["title"]["romaji"],
                    t2=choice2["title"]["romaji"],
                ),
                color=discord.Color.orange(),
            )

            file = await higherlower_combine.make_higherlower_combined_file(
                choice1, choice2, filename="duel.png"
            )
            view = HigherLowerView(ctx, choice1, choice2)
            if file:
                embed.set_image(url="attachment://duel.png")
                await ctx.send(embed=embed, view=view, file=file)
            else:
                await ctx.send(embed=embed, view=view)

            try:
                await view.wait()
            except asyncio.TimeoutError:
                await ctx.send(i18n.t("minigames.timeout_short", lg))
        finally:
            minigame_lock.end(uid)

    # --------------------------------------
    # Guess Year
    # --------------------------------------
    async def _guess_year(self, ctx: commands.Context) -> None:
        uid = ctx.author.id
        lg = i18n.ctx_lang(ctx)
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "guessyear"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            await ctx.send(i18n.t("minigames.gy_load", lg))
            linked = core.get_linked_username(uid)
            list_source = False
            user_list_fallback = False
            anime = None
            if linked:
                ml = core.fetch_user_list_media_for_minigames(linked)
                anime = core.pick_random_media_for_guess_year_from_list(ml)
                if anime:
                    list_source = True
                else:
                    user_list_fallback = True

            if not anime:
                for _ in range(5):
                    page = random.randint(1, 500)
                    query = '''
                    query ($page: Int) {
                      Page(perPage: 1, page: $page) {
                        media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                          title { romaji }
                          startDate { year }
                          coverImage { extraLarge }
                        }
                      }
                    }
                    '''
                    data = await core.query_anilist_async(query, {"page": page}, queue_ctx=ctx)
                    try:
                        candidate = data["data"]["Page"]["media"][0]
                        if candidate.get("startDate", {}).get("year"):
                            anime = candidate
                            break
                    except Exception:
                        continue

            if not anime:
                await ctx.send(core.anilist_error_user_message())
                return

            title = anime["title"]["romaji"]
            year = anime.get("startDate", {}).get("year")
            if not year:
                await ctx.send(i18n.t("minigames.gy_no_year", lg))
                return

            try:
                embed = discord.Embed(
                    title=i18n.t("minigames.gy_title", lg),
                    description=i18n.t("minigames.gy_desc", lg, title=title),
                    color=discord.Color.purple(),
                )
                base_tip = i18n.t("minigames.gy_footer_base", lg)
                if list_source:
                    embed.set_footer(
                        text=i18n.t("minigames.gy_footer_list", lg) + base_tip
                    )
                elif user_list_fallback and linked:
                    embed.set_footer(
                        text=i18n.t("minigames.gy_footer_fb", lg) + base_tip
                    )
                else:
                    embed.set_footer(text=base_tip)
                img_url = anime.get("coverImage", {}).get("extraLarge")
                if img_url:
                    embed.set_image(url=img_url)
                await ctx.send(embed=embed)

                def check(m: discord.Message) -> bool:
                    return m.author == ctx.author and m.channel == ctx.channel

                msg = await self.bot.wait_for("message", timeout=15.0, check=check)
                try:
                    guessed_year = int(msg.content.strip())
                    if abs(guessed_year - year) <= 1:
                        await ctx.send(i18n.t("minigames.gy_win", lg, year=year, guess=guessed_year))
                        await core.add_xp(self.bot, ctx.channel, ctx.author.id, 8)
                        core.add_mini_score(ctx.author.id, "guessyear", 1)
                        _mission_guess_win(self.bot, ctx.author.id)
                    else:
                        await ctx.send(i18n.t("minigames.gy_lose", lg, year=year, guess=guessed_year))
                except ValueError:
                    await ctx.send(i18n.t("minigames.gy_badfmt", lg, year=year))
            except (Exception, asyncio.TimeoutError):
                await ctx.send(i18n.t("minigames.gy_err", lg))
        finally:
            minigame_lock.end(uid)

    # --------------------------------------
    # Guess Episodes
    # --------------------------------------
    async def _guess_episodes(self, ctx: commands.Context) -> None:
        uid = ctx.author.id
        lg = i18n.ctx_lang(ctx)
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "guessepisodes"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            await ctx.send(i18n.t("minigames.ge_load", lg))
            linked = core.get_linked_username(uid)
            list_source = False
            user_list_fallback = False
            anime = None
            if linked:
                ml = core.fetch_user_list_media_for_minigames(linked)
                anime = core.pick_random_media_for_guess_episodes_from_list(ml)
                if anime:
                    list_source = True
                else:
                    user_list_fallback = True

            if not anime:
                for _ in range(5):
                    page = random.randint(1, 500)
                    query = '''
                    query ($page: Int) {
                      Page(perPage: 1, page: $page) {
                        media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                          title { romaji }
                          episodes
                          coverImage { extraLarge }
                        }
                      }
                    }
                    '''
                    data = await core.query_anilist_async(query, {"page": page}, queue_ctx=ctx)
                    try:
                        candidate = data["data"]["Page"]["media"][0]
                        if candidate.get("episodes") and isinstance(candidate.get("episodes"), int):
                            anime = candidate
                            break
                    except Exception:
                        continue

            if not anime:
                await ctx.send(core.anilist_error_user_message())
                return

            title = anime["title"]["romaji"]
            episodes = anime["episodes"]
            embed = discord.Embed(
                title=i18n.t("minigames.ge_title", lg),
                description=i18n.t("minigames.ge_desc", lg, title=title),
                color=discord.Color.blue(),
            )
            base_tip = i18n.t("minigames.ge_footer_base", lg)
            if list_source:
                embed.set_footer(
                    text=i18n.t("minigames.ge_footer_list", lg) + base_tip
                )
            elif user_list_fallback and linked:
                embed.set_footer(
                    text=i18n.t("minigames.ge_footer_fb", lg) + base_tip
                )
            else:
                embed.set_footer(text=base_tip)
            img_url = anime.get("coverImage", {}).get("extraLarge")
            if img_url:
                embed.set_image(url=img_url)
            await ctx.send(embed=embed)

            def check(m: discord.Message) -> bool:
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                msg = await self.bot.wait_for("message", timeout=20.0, check=check)
                try:
                    guessed = int(msg.content.strip())
                    tolerance = max(int(episodes * 0.1), 5)
                    if abs(guessed - episodes) <= tolerance:
                        await ctx.send(i18n.t("minigames.ge_win", lg, title=title, ep=episodes, guess=guessed))
                        await core.add_xp(self.bot, ctx.channel, ctx.author.id, 8)
                        core.add_mini_score(ctx.author.id, "guessepisodes", 1)
                        _mission_guess_win(self.bot, ctx.author.id)
                    else:
                        await ctx.send(i18n.t("minigames.ge_lose", lg, title=title, ep=episodes, guess=guessed))
                except ValueError:
                    await ctx.send(i18n.t("minigames.ge_badnum", lg, title=title, ep=episodes))
            except asyncio.TimeoutError:
                await ctx.send(i18n.t("minigames.ge_timeout", lg))
        finally:
            minigame_lock.end(uid)

    # --------------------------------------
    # Guess Genre
    # --------------------------------------
    async def _guess_genre(self, ctx: commands.Context) -> None:
        uid = ctx.author.id
        lg = i18n.ctx_lang(ctx)
        now = time.monotonic()
        cd_until = _GUESS_GENRE_COOLDOWN_UNTIL.get(uid, 0.0)
        if now < cd_until:
            remaining = max(1, int(cd_until - now))
            await minigame_lock.reply_guessgenre_cooldown(ctx, uid, remaining)
            return

        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "guessgenre"):
            await minigame_lock.reply_busy(ctx)
            return

        try:
            await ctx.send(i18n.t("minigames.gg_load", lg))
            anime = None
            linked = core.get_linked_username(uid)
            list_source = False
            user_list_fallback = False
            if linked:
                ml = core.fetch_user_list_media_for_minigames(linked)
                anime = core.pick_random_media_for_guess_genre_from_list(ml)
                if anime:
                    list_source = True
                else:
                    user_list_fallback = True

            if not anime:
                for _ in range(5):
                    page = random.randint(1, 500)
                    query = '''
                    query ($page: Int) {
                      Page(perPage: 1, page: $page) {
                        media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                          title { romaji }
                          genres
                          coverImage { extraLarge }
                        }
                      }
                    }
                    '''
                    data = await core.query_anilist_async(query, {"page": page}, queue_ctx=ctx)
                    try:
                        candidate = data["data"]["Page"]["media"][0]
                        if candidate.get("genres"):
                            anime = candidate
                            break
                    except Exception:
                        continue

            if not anime:
                await ctx.send(core.anilist_error_user_message())
                return

            title = anime["title"]["romaji"]
            genres = [g.lower() for g in anime.get("genres", [])]
            embed = discord.Embed(
                title=i18n.t("minigames.gg_title", lg),
                description=i18n.t(
                    "minigames.gg_desc",
                    lg,
                    title=title,
                    hint=_easy_genre_hint_short(lg),
                ),
                color=discord.Color.magenta(),
            )
            base_tip = i18n.t("minigames.gg_tip", lg)
            if list_source:
                footer_txt = (
                    i18n.t("minigames.gg_footer_list", lg)
                    + base_tip
                )
            elif user_list_fallback and linked:
                footer_txt = (
                    i18n.t("minigames.gg_footer_fb", lg)
                    + base_tip
                )
            else:
                footer_txt = base_tip
            embed.set_footer(text=footer_txt)
            img_url = anime.get("coverImage", {}).get("extraLarge")
            if img_url:
                embed.set_image(url=img_url)
            await ctx.send(embed=embed)

            def check(m: discord.Message) -> bool:
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                msg = await self.bot.wait_for("message", timeout=20.0, check=check)
                guess_raw = msg.content.strip()
                guess = guess_raw.lower()
                now2 = time.monotonic()

                # Même genre « facile » répété (bonne ou mauvaise réponse) : alertes salon puis sanction progressive
                if _guess_genre_is_spam_candidate(guess_raw):
                    key = _guess_genre_norm_key(guess_raw)
                    adq = _guess_genre_prune_attempt_dq(uid, now2)
                    adq.append((now2, key))
                    same_attempts = sum(1 for ts, k in adq if k == key)

                    if same_attempts == _ATTEMPT_SOFT_WARN:
                        await ctx.send(
                            i18n.t(
                                "minigames.gg_soft",
                                lg,
                                mention=ctx.author.mention,
                                guess=guess_raw,
                                hint=_easy_genre_hint_short(lg),
                            )
                        )
                    elif same_attempts == _ATTEMPT_HARD_WARN:
                        await ctx.send(
                            i18n.t(
                                "minigames.gg_hard",
                                lg,
                                guess=guess_raw,
                                hint=_easy_genre_hint_short(lg),
                            )
                        )

                    if same_attempts >= _ATTEMPT_PENALTY:
                        _GUESS_GENRE_STRIKES[uid] = _GUESS_GENRE_STRIKES.get(uid, 0) + 1
                        strike = _GUESS_GENRE_STRIKES[uid]
                        cd_sec = _genre_strike_cooldown_sec(uid)
                        xp_hit = _genre_strike_xp(uid)
                        _remove_attempt_key(uid, key)
                        _clear_guess_genre_streak_only(uid)
                        _GUESS_GENRE_COOLDOWN_UNTIL[uid] = now2 + cd_sec
                        await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp_hit, announce=False)
                        total_pen = core.inc_guess_genre_penalty_count(uid)
                        correct = guess in genres
                        genres_txt = ", ".join(anime["genres"])
                        if correct:
                            await ctx.send(
                                i18n.t(
                                    "minigames.gg_pen_ok",
                                    lg,
                                    guess=guess_raw,
                                    xp=xp_hit,
                                    cd=int(cd_sec),
                                    strike=strike,
                                    total=total_pen,
                                    title=title,
                                    genres=genres_txt,
                                )
                            )
                        else:
                            await ctx.send(
                                i18n.t(
                                    "minigames.gg_pen_bad",
                                    lg,
                                    guess=guess_raw,
                                    title=title,
                                    n=same_attempts,
                                    xp=xp_hit,
                                    cd=int(cd_sec),
                                    strike=strike,
                                    total=total_pen,
                                    genres=genres_txt,
                                )
                            )
                        return

                if guess in genres:
                    spam = _guess_genre_is_spam_candidate(guess_raw)
                    if spam:
                        dq = _guess_genre_prune_times(uid, now2)
                        dq.append(now2)
                        streak = _GUESS_GENRE_SPAM_STREAK.get(uid, 0) + 1
                        _GUESS_GENRE_SPAM_STREAK[uid] = streak
                        if streak == 2:
                            await ctx.send(
                                i18n.t("minigames.gg_spam2", lg, mention=ctx.author.mention)
                            )
                        elif streak == 3:
                            await ctx.send(
                                i18n.t("minigames.gg_spam3", lg)
                            )
                        penalize = streak > _SPAM_MAX_STREAK or len(dq) > _SPAM_MAX_IN_WINDOW
                        if penalize:
                            _GUESS_GENRE_STRIKES[uid] = _GUESS_GENRE_STRIKES.get(uid, 0) + 1
                            strike = _GUESS_GENRE_STRIKES[uid]
                            cd_sec = _genre_strike_cooldown_sec(uid)
                            xp_hit = _genre_strike_xp(uid)
                            _clear_guess_genre_streak_only(uid)
                            _GUESS_GENRE_COOLDOWN_UNTIL[uid] = now2 + cd_sec
                            await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp_hit, announce=False)
                            total_pen = core.inc_guess_genre_penalty_count(uid)
                            await ctx.send(
                                i18n.t(
                                    "minigames.gg_spam_pen",
                                    lg,
                                    guess=guess_raw,
                                    xp=xp_hit,
                                    cd=int(cd_sec),
                                    strike=strike,
                                    total=total_pen,
                                    title=title,
                                    genres=", ".join(anime["genres"]),
                                )
                            )
                        else:
                            await ctx.send(
                                i18n.t(
                                    "minigames.gg_exact",
                                    lg,
                                    title=title,
                                    genres=", ".join(anime["genres"]),
                                )
                            )
                            await core.add_xp(self.bot, ctx.channel, ctx.author.id, 5)
                            core.add_mini_score(ctx.author.id, "guessgenre", 1)
                            _mission_guess_win(self.bot, ctx.author.id)
                    else:
                        _GUESS_GENRE_SPAM_STREAK.pop(uid, None)
                        _GUESS_GENRE_SPAM_TIMES.pop(uid, None)
                        await ctx.send(
                            i18n.t(
                                "minigames.gg_exact",
                                lg,
                                title=title,
                                genres=", ".join(anime["genres"]),
                            )
                        )
                        await core.add_xp(self.bot, ctx.channel, ctx.author.id, 5)
                        core.add_mini_score(ctx.author.id, "guessgenre", 1)
                        _mission_guess_win(self.bot, ctx.author.id)
                else:
                    _GUESS_GENRE_SPAM_STREAK.pop(uid, None)
                    _GUESS_GENRE_SPAM_TIMES.pop(uid, None)
                    await ctx.send(
                        i18n.t(
                            "minigames.gg_wrong",
                            lg,
                            title=title,
                            genres=", ".join(anime["genres"]),
                        )
                    )
            except asyncio.TimeoutError:
                _clear_guess_genre_spam(uid)
                await ctx.send(i18n.t("minigames.ge_timeout", lg))
        finally:
            minigame_lock.end(uid)

    # --------------------------------------
    # Guess Character (boutons)
    # --------------------------------------
    async def _guess_character(self, ctx: commands.Context) -> None:
        uid = ctx.author.id
        lg = i18n.ctx_lang(ctx)
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        if not await anilist_gate.ensure_anilist_for_ctx(self.bot, ctx):
            return
        if not minigame_lock.try_begin(uid, "guesscharacter"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            linked = core.get_linked_username(uid)
            list_choice = core.build_guess_character_from_user_list(linked) if linked else None

            if list_choice:
                correct_name = list_choice["correct_name"]
                correct_image = list_choice["image_url"]
                correct_anime = list_choice["correct_anime"]
                options = list_choice["options"]
                correct_index = list_choice["correct_index"]
            else:
                page = random.randint(1, 100)
                query = '''
                query ($page: Int) {
                  Page(page: $page, perPage: 4) {
                    characters(sort: FAVOURITES_DESC) {
                      name { full }
                      image { large }
                      media(type: ANIME) {
                        nodes { title { romaji } }
                      }
                    }
                  }
                }
                '''
                data = await core.query_anilist_async(query, {"page": page}, queue_ctx=ctx)
                if not data or "data" not in data:
                    await ctx.send(core.anilist_error_user_message())
                    return

                characters = data["data"]["Page"]["characters"]
                if len(characters) < 4:
                    await ctx.send(i18n.t("minigames.gc_noperson", lg))
                    return

                correct = random.choice(characters)
                correct_name = correct["name"]["full"]
                correct_image = correct["image"]["large"]
                nodes = (correct.get("media", {}) or {}).get("nodes", [])
                correct_anime = (nodes[0]["title"]["romaji"] if nodes else "—")

                options = [c["name"]["full"] for c in characters]
                try:
                    correct_index = options.index(correct_name)
                except ValueError:
                    correct_index = random.randrange(len(options))

            embed = discord.Embed(
                title=i18n.t("minigames.gc_title", lg),
                description=i18n.t("minigames.gc_desc", lg),
                color=discord.Color.blurple()
            )
            if list_choice:
                embed.set_footer(
                    text=i18n.t("minigames.gc_footer_list", lg)
                )
            elif linked:
                embed.set_footer(
                    text=i18n.t("minigames.gc_footer_fb", lg)
                )
            embed.set_image(url=correct_image)

            class GCView(View):
                def __init__(self, *, timeout: float = 20):
                    super().__init__(timeout=timeout)
                    self.resolved = False
                    self.message: discord.Message | None = None

                async def on_timeout(self) -> None:
                    if self.resolved:
                        self.stop()
                        return
                    if not self.message:
                        self.stop()
                        return
                    self.resolved = True
                    for item in self.children:
                        if isinstance(item, Button):
                            item.disabled = True
                    await self.message.edit(
                        content=i18n.t(
                            "minigames.gc_timeout",
                            lg,
                            name=correct_name,
                            anime=correct_anime,
                        ),
                        view=self
                    )
                    self.stop()

            view = GCView(timeout=20)

            async def make_button_callback(inter: discord.Interaction, index: int):
                # Seul le lanceur peut cliquer
                if inter.user.id != ctx.author.id:
                    await inter.response.send_message(i18n.t("minigames.gc_not_yours", lg), ephemeral=True)
                    return

                if view.resolved:
                    try:
                        await inter.response.defer()
                    except Exception:
                        pass
                    return

                view.resolved = True
                for item in view.children:
                    if isinstance(item, Button):
                        item.disabled = True

                if index == correct_index:
                    txt = i18n.t(
                        "minigames.gc_win",
                        lg,
                        user=inter.user.display_name,
                        name=correct_name,
                        anime=correct_anime,
                    )
                    try:
                        await core.add_xp(self.bot, view.message.channel, inter.user.id, 5)
                    except Exception:
                        pass
                    try:
                        core.add_mini_score(inter.user.id, "guesscharacter", 1)
                        _mission_guess_win(self.bot, inter.user.id)
                    except Exception:
                        pass
                else:
                    txt = i18n.t(
                        "minigames.gc_lose",
                        lg,
                        name=correct_name,
                        anime=correct_anime,
                    )

                await inter.response.edit_message(content=txt, view=view)
                view.stop()

            for i, opt in enumerate(options):
                btn = Button(label=opt, style=discord.ButtonStyle.primary)
                async def _cb(inter: discord.Interaction, idx=i):
                    await make_button_callback(inter, idx)
                btn.callback = _cb
                view.add_item(btn)

            sent = await ctx.send(embed=embed, view=view)
            view.message = sent
            await view.wait()
        finally:
            minigame_lock.end(uid)

    @commands.hybrid_command(
        name="guessyear",
        description=ui_str("slash.minigames_guessyear"),
    )
    @commands.cooldown(1, 18, commands.BucketType.user)
    async def guessyear(self, ctx: commands.Context) -> None:
        await self._guess_year(ctx)

    @commands.hybrid_command(
        name="guessepisodes",
        description=ui_str("slash.minigames_guessepisodes"),
    )
    @commands.cooldown(1, 18, commands.BucketType.user)
    async def guessepisodes(self, ctx: commands.Context) -> None:
        await self._guess_episodes(ctx)

    @commands.hybrid_command(
        name="guessgenre",
        description=ui_str("slash.minigames_guessgenre"),
    )
    @commands.cooldown(1, 18, commands.BucketType.user)
    async def guessgenre(self, ctx: commands.Context) -> None:
        await self._guess_genre(ctx)

    @commands.hybrid_command(
        name="guesscharacter",
        description=ui_str("slash.minigames_guesscharacter"),
    )
    @commands.cooldown(1, 18, commands.BucketType.user)
    async def guesscharacter(self, ctx: commands.Context) -> None:
        await self._guess_character(ctx)

    @commands.hybrid_command(
        name="minijeux",
        description=ui_str("slash.minigames_minijeux"),
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def minijeux(self, ctx: commands.Context) -> None:
        lg = i18n.ctx_lang(ctx)
        em = discord.Embed(
            title=i18n.t("minigames.hub_title", lg),
            description=i18n.t("minigames.hub_desc", lg),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=em, view=MinijeuxHubView(self, ctx.author.id, lg))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiniGames(bot))
