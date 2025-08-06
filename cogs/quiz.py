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
from typing import Optional, Set, Dict, List, Tuple
from modules.core import normalize
import discord
from discord.ext import commands
from modules import core

logger = logging.getLogger(__name__)

class TitleMatcher:
    """Gestionnaire de correspondance des titres d'anime."""

    def __init__(self):
        self.cached_titles: Dict[str, Set[str]] = {}

    def clean_title(self, title: str) -> str:
        """Nettoie un titre pour la comparaison."""
        # Supprime les caractères spéciaux et la ponctuation
        cleaned = core.normalize(title)
        # Supprime les mots communs qui ne sont pas significatifs
        stop_words = {"the", "a", "an", "season", "part", "episode", "movie", "saison"}
        words = [w for w in cleaned.split() if w not in stop_words]
        return " ".join(words)

    def get_similarity(self, str1: str, str2: str) -> float:
        """Calcule la similarité entre deux chaînes."""
        return difflib.SequenceMatcher(None, str1, str2).ratio()

    def find_matches(self, guess: str, correct_titles: Set[str], threshold: float = 0.85) -> List[str]:
        """Trouve les correspondances possibles pour une réponse."""
        cleaned_guess = self.clean_title(guess)
        matches = []

        for title in correct_titles:
            cleaned_title = self.clean_title(title)

            # Vérification exacte
            if cleaned_guess == cleaned_title:
                return [title]

            # Vérification partielle
            if cleaned_guess in cleaned_title or cleaned_title in cleaned_guess:
                matches.append(title)
                continue

            # Vérification de similarité
            if self.get_similarity(cleaned_guess, cleaned_title) >= threshold:
                matches.append(title)

        return matches

class Quiz(commands.Cog):
    """Cog for anime quiz commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.title_matcher = TitleMatcher()

    async def _get_random_anime(self, sort_option: str = "SCORE_DESC") -> Optional[Dict]:
        """Fetch a random anime using the given sort option."""
        query = '''
        query ($page: Int, $sort: [MediaSort]) {
          Page(perPage: 1, page: $page) {
            media(type: ANIME, isAdult: false, sort: $sort) {
              id
              title { romaji english native }
              description(asHtml: false)
              coverImage { large extraLarge }
              genres
              meanScore
              popularity
              status
              season
              seasonYear
              episodes
            }
          }
        }
        '''
        for _ in range(10):
            try:
                page = random.randint(1, 500)
                data = core.query_anilist(query, {
                    "page": page,
                    "sort": sort_option
                })
                if data and "data" in data:
                    return data["data"]["Page"]["media"][0]
            except Exception as e:
                logger.error(f"Erreur lors de la récupération d'un anime: {e}")
                continue
        return None

    def _process_anime_titles(self, anime: Dict) -> Set[str]:
        """Traite les titres d'un anime pour la reconnaissance."""
        titles = set()
        title_data = anime["title"]

        # Ajouter tous les titres disponibles
        for key in ['romaji', 'english', 'native']:
            if title := title_data.get(key):
                titles.add(title)
                # Ajouter des variantes nettoyées
                titles.add(self.title_matcher.clean_title(title))

        return titles

    @commands.command(name="animequiz")
    async def animequiz(self, ctx: commands.Context, difficulty: str = "normal") -> None:
        """Lance un quiz pour deviner un anime à partir de son image."""
        try:
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

            # Création de l'embed
            embed = discord.Embed(
                title="❓ Quel est cet anime ?",
                description=(
                    "Tu as **20 secondes** pour deviner.\n"
                    "💡 Tu peux utiliser le titre en français, anglais ou japonais.\n"
                    "Tape `jsp` si tu veux passer."
                ),
                color=discord.Color.orange(),
            )

            # Utiliser la meilleure image disponible
            image_url = (anime.get("coverImage", {}).get("extraLarge") or
                         anime.get("coverImage", {}).get("large"))
            if image_url:
                embed.set_image(url=image_url)

            hint = "Genre" + ("s" if len(anime["genres"]) > 1 else "") + " : " + ", ".join(anime["genres"])
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
                        f"🇬🇧 {anime['title']['english']}" if anime['title']['english'] else None,
                        f"📝 {anime['title']['native']}" if anime['title']['native'] else None,
                    ]
                    titles = [t for t in titles if t]
                    await ctx.send(f"⏭️ Question passée. Les titres possibles étaient :\n{chr(10).join(titles)}")
                    return

                matches = self.title_matcher.find_matches(msg.content, correct_titles)
                if matches:
                    await ctx.send(f"✅ Bonne réponse, **{ctx.author.display_name}** !")

                    # Update scores and XP
                    scores = core.load_scores()
                    uid = str(ctx.author.id)
                    scores[uid] = scores.get(uid, 0) + 1
                    core.save_scores(scores)

                    xp_amount = 5 if difficulty == "easy" else 10 if difficulty == "normal" else 15
                    core.add_xp(ctx.author.id, xp_amount)
                    core.add_mini_score(ctx.author.id, "animequiz", 1)

                    # Show other possible titles
                    other_titles = [t for t in correct_titles if normalize(t) != normalize(msg.content)]
                    if other_titles:
                        await ctx.send(f"💡 Autres titres acceptés : {', '.join(other_titles)}")
                else:
                    titles = [
                        f"🇯🇵 {anime['title']['romaji']}",
                        f"🇬🇧 {anime['title']['english']}" if anime['title']['english'] else None,
                        f"📝 {anime['title']['native']}" if anime['title']['native'] else None,
                    ]
                    titles = [t for t in titles if t]
                    await ctx.send(f"❌ Mauvaise réponse. C'était :\n{chr(10).join(titles)}")

            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était **{anime['title']['romaji']}**.")

        except Exception as e:
            logger.error(f"Erreur dans animequiz: {e}")
            await ctx.send("❌ Une erreur s'est produite lors du quiz.")

    @commands.command(name="animequizmulti")
    async def animequizmulti(self, ctx: commands.Context, nb_questions: int = 5) -> None:
        """Lance un quiz multi questions (1 à 20)."""
        try:
            if not 1 <= nb_questions <= 20:
                await ctx.send("❌ Tu dois choisir un nombre entre 1 et 20.")
                return

            await ctx.send(f"🎮 Lancement de **{nb_questions} questions** pour **{ctx.author.display_name}**...")
            difficulties = ["easy", "normal", "hard"]
            score = 0
            total_xp = 0

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
                    embed.set_footer(text=f"Genres : {', '.join(anime['genres'])}")

                    await ctx.send(embed=embed)

                    try:
                        msg = await self.bot.wait_for(
                            "message",
                            timeout=20.0,
                            check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                        )

                        if msg.content.strip().lower() == "jsp":
                            await ctx.send(f"⏭️ Passé. C'était **{anime['title']['romaji']}**.")
                        else:
                            matches = self.title_matcher.find_matches(msg.content, correct_titles)
                            if matches:
                                await ctx.send("✅ Bonne réponse !")
                                score += 1
                                xp_gain = 5 if difficulty == "easy" else 10 if difficulty == "normal" else 15
                                total_xp += xp_gain
                                core.add_mini_score(ctx.author.id, "animequiz", 1)
                            else:
                                await ctx.send(f"❌ Faux ! C'était **{anime['title']['romaji']}**.")

                    except asyncio.TimeoutError:
                        await ctx.send(f"⏰ Temps écoulé ! C'était **{anime['title']['romaji']}**.")

                except Exception as e:
                    logger.error(f"Erreur question {i + 1}: {e}")
                    continue

                await asyncio.sleep(1.5)

            # Résultats finaux
            scores = core.load_scores()
            uid = str(ctx.author.id)

            # Pénalité si moins de 50% de bonnes réponses
            if score < (nb_questions / 2):
                penalty = 1
                scores[uid] = max(0, scores.get(uid, 0) - penalty)
                await ctx.send(f"⚠️ Tu as fait moins de 50% de bonnes réponses, -{penalty} point retiré.")
            else:
                scores[uid] = scores.get(uid, 0) + score

            core.save_scores(scores)
            core.add_xp(ctx.author.id, total_xp)

            # Embed de résultat final
            embed = discord.Embed(
                title="🏁 Quiz terminé !",
                description=(
                    f"Score final : **{score}/{nb_questions}**\n"
                    f"XP gagnés : **{total_xp}**\n"
                    f"Précision : **{(score / nb_questions * 100):.1f}%**"
                ),
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans animequizmulti: {e}")
            await ctx.send("❌ Une erreur s'est produite durant le quiz.")

    @commands.command(name="duel")
    async def duel(self, ctx: commands.Context, opponent: discord.Member) -> None:
        """Affronte un ami en duel de 3 questions."""
        try:
            if opponent.bot:
                await ctx.send("🤖 Tu ne peux pas défier un bot.")
                return

            if opponent == ctx.author:
                await ctx.send("🙃 Tu ne peux pas te défier toi-même.")
                return

            # Annonce du duel
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
                    # Préparation de la question
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

                    # Création de l'embed
                    embed = discord.Embed(
                        title=f"🎮 Duel – Question {i + 1}/3",
                        description=(
                            "**Le plus rapide à répondre gagne !**\n"
                            "Vous avez 15 secondes. Tapez `jsp` pour passer."
                        ),
                        color=discord.Color.red(),
                    )

                    if image := (anime.get("coverImage", {}).get("extraLarge") or
                                 anime.get("coverImage", {}).get("large")):
                        embed.set_image(url=image)

                    embed.set_footer(text=f"Genres : {', '.join(anime['genres'])}")
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

            # Résultats du duel
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
                core.add_xp(winner.id, 20)
                core.add_mini_score(winner.id, "duel", 1)

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans duel: {e}")
            await ctx.send("❌ Une erreur s'est produite pendant le duel.")

    @commands.command(name="quiztop")
    async def quiztop(self, ctx: commands.Context) -> None:
        """Affiche le top 10 des scores du quiz."""
        try:
            scores = core.load_scores()
            if not scores:
                await ctx.send("🏆 Aucun score enregistré pour l'instant.")
                return

            # Préparation du classement
            leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]

            embed = discord.Embed(
                title="🏆 Classement Anime Quiz",
                color=discord.Color.gold()
            )

            # Construction du classement
            lines = []
            for i, (uid, score) in enumerate(leaderboard, 1):
                try:
                    user = await self.bot.fetch_user(int(uid))
                    title = core.get_title_for_level(score)
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👑"
                    lines.append(f"{medal} **{user.display_name}** — {score} pts\n➥ *{title}*")
                except Exception as e:
                    logger.error(f"Erreur récupération utilisateur {uid}: {e}")
                    continue

            embed.description = "\n\n".join(lines) if lines else "Aucun score."

            # Informations supplémentaires
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

            # Compteur avant reset
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

    @commands.command(name="myrank")
    async def myrank(self, ctx: commands.Context) -> None:
        """Affiche ton rang, ton XP et ton titre."""
        try:
            # Chargement des données
            levels = core.load_levels()
            scores = core.load_scores()

            user_data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
            quiz_score = scores.get(str(ctx.author.id), 0)

            xp = user_data["xp"]
            level = user_data["level"]
            next_xp = (level + 1) * 100

            # Création de l'embed
            embed = discord.Embed(
                title=f"🏅 Rang de {ctx.author.display_name}",
                color=discord.Color.purple()
            )

            # Barre de progression
            progress = core.get_xp_bar(xp, next_xp)
            title = core.get_title_for_level(level)

            embed.add_field(
                name="📊 Progression",
                value=(
                    f"**Niveau {level}** ({xp}/{next_xp} XP)\n"
                    f"`{progress}`\n"
                    f"Titre actuel : **{title}**"
                ),
                inline=False
            )

            # Position dans le classement
            if quiz_score > 0:
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                position = next(i for i, (uid, _) in enumerate(sorted_scores, 1) if uid == str(ctx.author.id))
                embed.add_field(
                    name="🏆 Classement Quiz",
                    value=f"Position : **#{position}**\nScore total : **{quiz_score}** points",
                    inline=False
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erreur dans myrank: {e}")
            await ctx.send("❌ Une erreur s'est produite.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quiz(bot))
