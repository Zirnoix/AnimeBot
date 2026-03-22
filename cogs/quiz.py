"""
Quiz and duel commands (AniList live).

- /animequiz  (choices de difficulté)
- /animequizmulti
- /duel       (choices manches + difficulté)
- /quiztop
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
import difflib
from datetime import datetime, timedelta, timezone
from typing import Optional, Set, Dict, List, Any

import discord
from discord.ext import commands
from discord import app_commands

from modules import core
from modules.core import normalize

logger = logging.getLogger(__name__)

# --- petit utilitaire pour éviter "This interaction failed" côté slash ---
async def _maybe_defer(ctx: commands.Context, ephemeral: bool = False) -> None:
    try:
        if hasattr(ctx, "interaction") and ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(ephemeral=ephemeral, thinking=True)
    except Exception:
        pass

# --- paramètres DUEL ---
ANSWER_TIMEOUT = 25  # secondes par manche
IGNORED_ANSWERS: Set[str] = {"jsp", "je sais pas", "idk", "skip", "pass", "aucune idée", "dk"}
_active_duels_per_channel: Dict[int, bool] = {}  # anti-chevauchement par salon


def _is_jsp(guess: str) -> bool:
    """Réponse type « je passe » (jsp) pour le duel — aligné sur IGNORED_ANSWERS."""
    return (guess or "").strip().lower() in IGNORED_ANSWERS

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

    def __init__(self):
        self.cached_titles: Dict[str, Set[str]] = {}

    def clean_title(self, title: str) -> str:
        cleaned = core.normalize(title)
        stop_words = {"the", "a", "an", "season", "part", "episode", "movie", "saison"}
        words = [w for w in cleaned.split() if w not in stop_words]
        return " ".join(words)

    def get_similarity(self, str1: str, str2: str) -> float:
        return difflib.SequenceMatcher(None, str1, str2).ratio()

    def find_matches(self, guess: str, correct_titles: Set[str], threshold: float = 0.85) -> List[str]:
        cleaned_guess = self.clean_title(guess)
        matches: List[str] = []
        for title in correct_titles:
            cleaned_title = self.clean_title(title)
            if cleaned_guess == cleaned_title:
                return [title]
            if cleaned_guess in cleaned_title or cleaned_title in cleaned_guess:
                matches.append(title)
                continue
            if self.get_similarity(cleaned_guess, cleaned_title) >= threshold:
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


class Quiz(commands.Cog):
    """Cog for anime quiz commands (AniList live)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.title_matcher = TitleMatcher()

    # ---------- AniList live picker ----------
    async def _fetch_random_anilist_media(self, sort: str) -> Optional[Dict[str, Any]]:
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
        data = core.query_anilist(query_count, variables) or {}
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
        data2 = core.query_anilist(query_pick, variables) or {}
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
    @app_commands.describe(difficulty="Choisis la difficulté")
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="Easy 😌",   value="easy"),
            app_commands.Choice(name="Medium 😼", value="medium"),
            app_commands.Choice(name="Hard 🔥",   value="hard"),
        ]
    )
    async def animequiz(self, ctx: commands.Context, difficulty: str = "medium") -> None:
        try:
            await _maybe_defer(ctx)
            await ctx.send("🎮 Préparation du quiz...")

            sort_option = SORT_BY_DIFF.get((difficulty or "medium").lower(), "SCORE_DESC")

            anime = await self._fetch_random_anilist_media(sort_option)
            if not anime:
                await ctx.send("❌ Impossible de trouver un anime correspondant (AniList). Réessaie.")
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
            if genres:
                embed.set_footer(text=f"Genres : {', '.join(genres)}")
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
                    return

                if self.title_matcher.find_matches(guess, correct_titles):
                    await ctx.send(f"✅ Bonne réponse, **{ctx.author.display_name}** !")

                    # scoreboard + xp
                    scores = core.load_scores()
                    uid = str(ctx.author.id)
                    scores[uid] = scores.get(uid, 0) + 1
                    core.save_scores(scores)

                    xp_amount = 5 if difficulty == "easy" else 10 if difficulty == "medium" else 15
                    await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp_amount)
                    core.add_mini_score(ctx.author.id, "animequiz", 1)

                    # Missions
                    ctx.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_win")
                    ctx.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_solo_ok")

                    other_titles = [t for t in correct_titles if normalize(t) != normalize(guess)]
                    if other_titles:
                        await ctx.send(f"💡 Autres titres acceptés : {', '.join(other_titles)}")
                else:
                    await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title'].get('romaji')}**.")

            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était **{anime['title'].get('romaji')}**.")

        except Exception as e:
            logger.error(f"Erreur dans animequiz: {e}")
            await ctx.send("❌ Une erreur s'est produite lors du quiz.")

    @commands.hybrid_command(name="animequizmulti", description="Quiz multi (1 à 20) — easy/medium/hard aléatoires.")
    async def animequizmulti(self, ctx: commands.Context, nb_questions: int = 5) -> None:
        try:
            await _maybe_defer(ctx)
            if not 1 <= nb_questions <= 20:
                await ctx.send("❌ Choisis un nombre entre 1 et 20.")
                return

            await ctx.send(f"🎮 Lancement de **{nb_questions} questions**…")
            diffs = ["easy", "medium", "hard"]
            score = 0
            total_xp = 0
            combo = 0
            combo_bonus_total = 0

            for i in range(nb_questions):
                try:
                    difficulty = random.choice(diffs)
                    sort_option = SORT_BY_DIFF.get(difficulty, "SCORE_DESC")

                    anime = await self._fetch_random_anilist_media(sort_option)
                    if not anime:
                        await asyncio.sleep(0.6)
                        continue

                    correct_titles = self._titles_set(anime)
                    image = (anime.get("coverImage", {}) or {}).get("extraLarge") or (anime.get("coverImage", {}) or {}).get("large")

                    embed = discord.Embed(
                        title=f"❓ Q{i+1}/{nb_questions} — difficulté `{difficulty}`",
                        description="Tu as **20s**. Tape `jsp` pour passer.",
                        color=discord.Color.orange(),
                    )
                    if image:
                        embed.set_image(url=image)
                    if anime.get("genres"):
                        embed.set_footer(text=f"Genres : {', '.join(anime['genres'])}")
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
                                await ctx.send("✅ Bonne réponse !")
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

            # scoreboard global
            scores = core.load_scores()
            uid = str(ctx.author.id)
            if score < (nb_questions / 2):
                penalty = 1
                scores[uid] = max(0, scores.get(uid, 0) - penalty)
                await ctx.send(f"⚠️ Moins de 50% de bonnes réponses, -{penalty} point retiré.")
            else:
                scores[uid] = scores.get(uid, 0) + score
            core.save_scores(scores)

            total_xp += combo_bonus_total
            if total_xp > 0:
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, total_xp)

            precision = (score / nb_questions * 100) if nb_questions > 0 else 0.0
            # Mission: win multi si ≥ 50%
            if score >= max(1, nb_questions // 2):
                self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_win")

            embed = discord.Embed(
                title="🏁 Quiz terminé !",
                description=(
                    f"Score final : **{score}/{nb_questions}**\n"
                    f"XP gagnés : **{total_xp}** *(dont **{combo_bonus_total}** en combos)*\n"
                    f"Précision : **{precision:.1f}%**"
                ),
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans animequizmulti: {e}")
            await ctx.send("❌ Une erreur s'est produite durant le quiz.")

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
        try:
            await _maybe_defer(ctx)
    
            # Garde-fous
            if opponent.bot:
                await ctx.send("🤖 Tu ne peux pas défier un bot.")
                return
            if opponent.id == ctx.author.id:
                await ctx.send("🙃 Tu ne peux pas te défier toi-même.")
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
                anime = await self._fetch_random_anilist_media(sort_option)
                if not anime:
                    await ctx.send("❌ Impossible de récupérer une question, manche annulée.")
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
                if genres:
                    embed.set_footer(text=f"Genres : {', '.join(genres)}")
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


    @commands.hybrid_command(name="quiztop", description="Top quiz du mois en cours + vainqueur du mois dernier.")
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

            # Vainqueur du mois dernier (écrit par quiz_reset)
            w = core.load_winner()  # {"month":"YYYY-MM","winner_user_id": "...", "winner_score": int}
            if w and w.get("month"):
                label = core.human_month_fr(w["month"])
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
            em.set_footer(text=f"⏳ Prochain reset : {nxt:%d/%m %H:%M} • dans {left}")

            await ctx.send(embed=em)

        except Exception as e:
            logger.error(f"Erreur dans quiztop: {e}")
            await ctx.send("❌ Une erreur s'est produite.")

    @commands.hybrid_command(name="myrank", description="Affiche ton rang, ton XP et ton titre.")
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
            title = core.get_title_for_global_level(level)

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
                quiz_title = core.get_title_for_quiz_score(quiz_score)
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

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans myrank: {e}")
            await ctx.send("❌ Une erreur s'est produite.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quiz(bot))
