"""
Quiz and duel commands.

This cog implements anime guessing games and scoreboards. Users can
participate in solo quizzes, multi-question quizzes, or challenge
friends to duels. Scores and levels are persisted via ``modules.core``.
"""

from __future__ import annotations

import random
import asyncio
import logging
import difflib
from datetime import datetime
from typing import Optional, Set, Dict, List, Tuple, Any

import discord
from discord.ext import commands
from modules import core
from modules.core import normalize, FileConfig

logger = logging.getLogger(__name__)

# --- petit utilitaire pour éviter "This interaction failed" côté slash ---
async def _maybe_defer(ctx: commands.Context, ephemeral: bool = False) -> None:
    try:
        # ctx.interaction existe quand la commande est appelée en slash
        if hasattr(ctx, "interaction") and ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(ephemeral=ephemeral)
    except Exception:
        pass


class TitleMatcher:
    """Gestionnaire de correspondance des titres d'anime."""

    def __init__(self):
        self.cached_titles: Dict[str, Set[str]] = {}

    def clean_title(self, title: str) -> str:
        """Nettoie un titre pour la comparaison."""
        cleaned = core.normalize(title)
        stop_words = {"the", "a", "an", "season", "part", "episode", "movie", "saison"}
        words = [w for w in cleaned.split() if w not in stop_words]
        return " ".join(words)

    def get_similarity(self, str1: str, str2: str) -> float:
        """Calcule la similarité entre deux chaînes."""
        return difflib.SequenceMatcher(None, str1, str2).ratio()

    def find_matches(self, guess: str, correct_titles: Set[str], threshold: float = 0.85) -> List[str]:
        """Trouve les correspondances possibles pour une réponse."""
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


class Quiz(commands.Cog):
    """Cog for anime quiz commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.title_matcher = TitleMatcher()

    async def _get_random_anime(self, sort_option: str = "SCORE_DESC") -> Optional[Dict[str, Any]]:
        """
        Sélectionne un anime aléatoire depuis le cache local.
        TODO: si tu veux exploiter sort_option (SCORE_DESC / POPULARITY_DESC / etc.),
        filtre/pondère ici le choix dans anime_list.
        """
        anime_list = core.load_cached_titles()  # doit renvoyer une liste de dicts
        if not anime_list:
            return None
        return random.choice(anime_list)

    def _process_anime_titles(self, anime: Dict[str, Any]) -> Set[str]:
        """
        Retourne l'ensemble des titres acceptés pour un anime.
        Inclut romaji/english/native + éventuels synonyms si dispo.
        """
        titles: Set[str] = set()

        t = anime.get("title") or {}
        r = t.get("romaji")
        e = t.get("english")
        n = t.get("native")
        if r: titles.add(r)
        if e: titles.add(e)
        if n: titles.add(n)

        syns = anime.get("synonyms") or []
        for syn in syns:
            if syn:
                titles.add(syn)

        return titles

    # ---------- COMMANDES HYBRIDES (fonctionnent en / ET en !) ----------

    @commands.hybrid_command(name="animequiz", description="Lance un quiz pour deviner un anime à partir de son image.")
    async def animequiz(self, ctx: commands.Context, difficulty: str = "normal") -> None:
        """Lance un quiz pour deviner un anime à partir de son image."""
        try:
            await _maybe_defer(ctx)
            await ctx.send("🎮 Préparation du quiz...")

            difficulty = difficulty.lower()
            sort_option = {
                "easy": "POPULARITY_DESC",
                "normal": "SCORE_DESC",
                "hard": "TRENDING_DESC",
            }.get(difficulty, "SCORE_DESC")

            anime = await self._get_random_anime(sort_option)
            if not anime:
                await ctx.send("❌ Aucun anime trouvé.")
                return

            correct_titles = self._process_anime_titles(anime)

            embed = discord.Embed(
                title="❓ Quel est cet anime ?",
                description=(
                    "Tu as **20 secondes** pour deviner.\n"
                    "💡 Tu peux utiliser le titre en français, anglais ou japonais.\n"
                    "Tape jsp si tu veux passer."
                ),
                color=discord.Color.orange(),
            )

            image_url = (anime.get("coverImage", {}).get("extraLarge") or
                         anime.get("coverImage", {}).get("large"))
            if image_url:
                embed.set_image(url=image_url)

            genres = anime.get("genres", [])
            hint = ("Genre" + ("s" if len(genres) > 1 else "") + " : " + ", ".join(genres)) if genres else "Bonne chance !"
            embed.set_footer(text=hint)

            await ctx.send(embed=embed)

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=20.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                )

                if msg.content.strip().lower() == "jsp":
                    titles = [
                        f"🇯🇵 {anime['title']['romaji']}",
                        f"🇬🇧 {anime['title']['english']}" if anime['title'].get('english') else None,
                        f"📝 {anime['title']['native']}" if anime['title'].get('native') else None,
                    ]
                    titles = [t for t in titles if t]
                    await ctx.send(f"⏭️ Question passée. Les titres possibles étaient :\n{chr(10).join(titles)}")
                    return

                matches = self.title_matcher.find_matches(msg.content, correct_titles)
                if matches:
                    await ctx.send(f"✅ Bonne réponse, **{ctx.author.display_name}** !")

                    scores = core.load_scores()
                    uid = str(ctx.author.id)
                    scores[uid] = scores.get(uid, 0) + 1
                    core.save_scores(scores)

                    xp_amount = 5 if difficulty == "easy" else 10 if difficulty == "normal" else 15
                    await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp_amount)
                    core.add_mini_score(ctx.author.id, "animequiz", 1)

                    ctx.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_solo_ok")

                    other_titles = [t for t in correct_titles if normalize(t) != normalize(msg.content)]
                    if other_titles:
                        await ctx.send(f"💡 Autres titres acceptés : {', '.join(other_titles)}")
                else:
                    titles = [
                        f"🇯🇵 {anime['title']['romaji']}",
                        f"🇬🇧 {anime['title']['english']}" if anime['title'].get('english') else None,
                        f"📝 {anime['title']['native']}" if anime['title'].get('native') else None,
                    ]
                    titles = [t for t in titles if t]
                    await ctx.send(f"❌ Mauvaise réponse. C'était :\n{chr(10).join(titles)}")

            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était **{anime['title']['romaji']}**.")

        except Exception as e:
            logger.error(f"Erreur dans animequiz: {e}")
            await ctx.send("❌ Une erreur s'est produite lors du quiz.")

    @commands.hybrid_command(name="animequizmulti", description="Lance un quiz multi-questions (1 à 20) avec bonus de combo.")
    async def animequizmulti(self, ctx: commands.Context, nb_questions: int = 5) -> None:
        """Lance un quiz multi questions (1 à 20) avec bonus de combo."""
        try:
            await _maybe_defer(ctx)
            if not 1 <= nb_questions <= 20:
                await ctx.send("❌ Tu dois choisir un nombre entre 1 et 20.")
                return

            await ctx.send(f"🎮 Lancement de **{nb_questions} questions** pour **{ctx.author.display_name}**...")
            difficulties = ["easy", "normal", "hard"]
            score = 0
            total_xp = 0

            combo = 0
            combo_bonus_total = 0

            for i in range(nb_questions):
                try:
                    difficulty = random.choice(difficulties)
                    sort_option = {
                        "easy": "POPULARITY_DESC",
                        "normal": "SCORE_DESC",
                        "hard": "TRENDING_DESC",
                    }[difficulty]

                    anime = await self._get_random_anime(sort_option)
                    if not anime:
                        continue

                    correct_titles = self._process_anime_titles(anime)
                    image = (anime.get("coverImage", {}).get("extraLarge") or
                             anime.get("coverImage", {}).get("large"))

                    embed = discord.Embed(
                        title=f"❓ Question {i + 1}/{nb_questions} — difficulté `{difficulty}`",
                        description="Tu as **20 secondes** pour deviner. Tape `jsp` pour passer.",
                        color=discord.Color.orange(),
                    )
                    if image:
                        embed.set_image(url=image)
                    embed.set_footer(text=f"Genres : {', '.join(anime.get('genres', []))}")

                    await ctx.send(embed=embed)

                    try:
                        msg = await self.bot.wait_for(
                            "message",
                            timeout=20.0,
                            check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                        )

                        if msg.content.strip().lower() == "jsp":
                            await ctx.send(f"⏭️ Passé. C'était **{anime['title']['romaji']}**.")
                            combo = 0
                        else:
                            matches = self.title_matcher.find_matches(msg.content, correct_titles)
                            if matches:
                                await ctx.send("✅ Bonne réponse !")
                                score += 1
                                xp_gain = 5 if difficulty == "easy" else 10 if difficulty == "normal" else 15
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
                                await ctx.send(f"❌ Faux ! C'était **{anime['title']['romaji']}**.")
                                combo = 0

                    except asyncio.TimeoutError:
                        await ctx.send(f"⏰ Temps écoulé ! C'était **{anime['title']['romaji']}**.")
                        combo = 0

                except Exception as e:
                    logger.error(f"Erreur question {i + 1}: {e}")
                    continue

                await asyncio.sleep(1.5)

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
            embed = discord.Embed(
                title="🏁 Quiz terminé !",
                description=(
                    f"Score final : **{score}/{nb_questions}**\n"
                    f"XP gagnés : **{total_xp}** *(dont **{combo_bonus_total}** de bonus combo)*\n"
                    f"Précision : **{precision:.1f}%**"
                ),
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans animequizmulti: {e}")
            await ctx.send("❌ Une erreur s'est produite durant le quiz.")

    @commands.hybrid_command(name="duel", description="Affronte un ami en duel de 3 questions.")
    async def duel(self, ctx: commands.Context, opponent: discord.Member) -> None:
        """Affronte un ami en duel de 3 questions."""
        try:
            await _maybe_defer(ctx)
            if opponent.bot:
                await ctx.send("🤖 Tu ne peux pas défier un bot.")
                return

            if opponent == ctx.author:
                await ctx.send("🙃 Tu ne peux pas te défier toi-même.")
                return

            embed = discord.Embed(
                title="⚔️ Défi de quiz anime !",
                description=f"**{ctx.author.display_name}** défie **{opponent.display_name}** !\n"
                            f"3 questions, le plus rapide gagne !",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

            players = [ctx.author, opponent]
            scores = {ctx.author.id: 0, opponent.id: 0}
            difficulties = ["easy", "normal", "hard"]

            for i in range(3):
                try:
                    difficulty = random.choice(difficulties)
                    sort_option = {
                        "easy": "POPULARITY_DESC",
                        "normal": "SCORE_DESC",
                        "hard": "TRENDING_DESC",
                    }[difficulty]

                    anime = await self._get_random_anime(sort_option)
                    if not anime:
                        continue

                    correct_titles = self._process_anime_titles(anime)

                    embed = discord.Embed(
                        title=f"🎮 Duel – Question {i + 1}/3",
                        description=(
                            "**Le plus rapide à répondre gagne !**\n"
                            "Vous avez 15 secondes. Tapez `jsp` pour passer."
                        ),
                        color=discord.Color.red(),
                    )

                    image = (anime.get("coverImage", {}).get("extraLarge") or
                             anime.get("coverImage", {}).get("large"))
                    if image:
                        embed.set_image(url=image)

                    genres = anime.get("genres", [])
                    if genres:
                        embed.set_footer(text=f"Genres : {', '.join(genres)}")

                    await ctx.send(embed=embed)

                    def check(m: discord.Message) -> bool:
                        return m.author in players and m.channel == ctx.channel

                    try:
                        msg = await self.bot.wait_for("message", timeout=15.0, check=check)
                        answer = msg.content.strip()

                        if answer.lower() == "jsp":
                            await ctx.send(f"⏭️ Question passée. C'était **{anime['title']['romaji']}**.")
                        else:
                            matches = self.title_matcher.find_matches(answer, correct_titles)
                            if matches:
                                scores[msg.author.id] += 1
                                await ctx.send(f"✅ Bonne réponse de **{msg.author.display_name}** !")
                            else:
                                await ctx.send(f"❌ Mauvaise réponse. C'était **{anime['title']['romaji']}**.")

                    except asyncio.TimeoutError:
                        await ctx.send(f"⏰ Temps écoulé ! C'était **{anime['title']['romaji']}**.")

                except Exception as e:
                    logger.error(f"Erreur question duel {i + 1}: {e}")
                    continue

                await asyncio.sleep(1)

            s1, s2 = scores[ctx.author.id], scores[opponent.id]

            embed = discord.Embed(
                title="🏆 Résultats du duel !",
                color=discord.Color.gold()
            )

            if s1 == s2:
                embed.description = f"🤝 **Égalité parfaite : {s1} - {s2}**"
            else:
                winner = ctx.author if s1 > s2 else opponent
                loser = opponent if winner == ctx.author else ctx.author
                embed.description = (
                    f"Victoire de **{winner.display_name}** !\n"
                    f"**{ctx.author.display_name}** {s1} - {s2} **{opponent.display_name}**\n"
                    f"🎖️ +20 XP pour le vainqueur !"
                )
                await core.add_xp(self.bot, ctx.channel, winner.id, 20)  # (petite correction logique)

                core.add_mini_score(winner.id, "duel", 1)

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans duel: {e}")
            await ctx.send("❌ Une erreur s'est produite pendant le duel.")

    @commands.hybrid_command(name="quiztop", description="Affiche le top 10 des scores du quiz.")
    async def quiztop(self, ctx: commands.Context) -> None:
        """Affiche le top 10 des scores du quiz."""
        try:
            await _maybe_defer(ctx, ephemeral=False)
            scores = core.load_scores()
            if not scores:
                await ctx.send("🏆 Aucun score enregistré pour l'instant.")
                return

            leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]

            embed = discord.Embed(
                title="🏆 Classement Anime Quiz",
                color=discord.Color.gold()
            )

            lines: List[str] = []
            for i, (uid, score) in enumerate(leaderboard, 1):
                try:
                    user = await self.bot.fetch_user(int(uid))
                    title = core.get_title_for_quiz_score(score)
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👑"
                    lines.append(f"{medal} **{user.display_name}** — {score} pts\n➥ *{title}*")
                except Exception as e:
                    logger.error(f"Erreur récupération utilisateur {uid}: {e}")
                    continue

            embed.description = "\n\n".join(lines) if lines else "Aucun score."

            winner_data = core.load_json(core.WINNER_FILE, None)
            if winner_data:
                try:
                    winner_user = await self.bot.fetch_user(int(winner_data["uid"]))
                    won_at = datetime.fromisoformat(winner_data["timestamp"])
                    month = won_at.strftime("%B %Y")
                    embed.add_field(
                        name="🏅 Vainqueur du mois dernier",
                        value=f"**{winner_user.display_name}**\n{month}",
                        inline=False
                    )
                except Exception:
                    pass

            now = datetime.now(tz=core.TIMEZONE)
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_month = now.replace(month=now.month + 1, day=1)

            next_month = next_month.replace(hour=0, minute=0, second=0, microsecond=0)
            delta = next_month - now

            embed.add_field(
                name="⏳ Prochain reset",
                value=f"Dans {delta.days} jour(s) et {delta.seconds // 3600} heure(s)",
                inline=False
            )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans quiztop: {e}")
            await ctx.send("❌ Une erreur s'est produite.")

    @commands.hybrid_command(name="myrank", description="Affiche ton rang, ton XP et ton titre.")
    async def myrank(self, ctx: commands.Context) -> None:
        """Affiche ton rang, ton XP et ton titre."""
        try:
            await _maybe_defer(ctx, ephemeral=False)
            levels = core.load_levels()
            scores = core.load_scores()

            user_data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
            quiz_score = scores.get(str(ctx.author.id), 0)

            xp = user_data["xp"]
            level = user_data["level"]
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
