"""
Quiz and duel commands.

This cog implements anime guessing games and scoreboards. Users can
participate in solo quizzes, multi-question quizzes, or challenge
friends to duels. Scores and levels are persisted via ``modules.core``.
"""

from __future__ import annotations

import random
import asyncio
from datetime import datetime

import discord
from discord.ext import commands

from ..modules import core


class Quiz(commands.Cog):
    """Cog for anime quiz commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _get_random_anime(self, sort_option: str = "SCORE_DESC") -> dict | None:
        """Fetch a random anime using the given sort option."""
        for _ in range 10:
            page = random.randint(1, 500)
            query = f'''
            query {{
              Page(perPage: 1, page: {page}) {{
                media(type: ANIME, isAdult: false, sort: {sort_option}) {{
                  id
                  title {{ romaji english native }}
                  description(asHtml: false)
                  coverImage {{ large extraLarge }}
                }}
              }}
            }}
            '''
            data = core.query_anilist(query)
            try:
                return data["data"]["Page"]["media"][0]
            except Exception:
                continue
        return None

    @commands.command(name="animequiz")
    async def animequiz(self, ctx: commands.Context, difficulty: str = "normal") -> None:
        """Lance un quiz pour deviner un anime à partir de son image.

        ``difficulty`` peut être ``easy``, ``normal`` ou ``hard`` et influe
        sur la façon dont les animes sont sélectionnés.
        """
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
        correct_titles = set(core.title_variants(anime["title"]))
        embed = discord.Embed(
            title="❓ Quel est cet anime ?",
            description="Tu as **20 secondes** pour deviner. Tape `jsp` si tu veux passer.",
            color=discord.Color.orange(),
        )
        # Prefer extraLarge if available
        image_url = anime.get("coverImage", {}).get("extraLarge") or anime.get("coverImage", {}).get("large")
        if image_url:
            embed.set_image(url=image_url)
        await ctx.send(embed=embed)
        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await self.bot.wait_for("message", timeout=20.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était **{anime['title']['romaji']}**.")
            return
        user_input = core.normalize(msg.content)
        if user_input == "jsp":
            await ctx.send(f"⏭️ Question passée. La bonne réponse était **{anime['title']['romaji']}**.")
            return
        if user_input in correct_titles:
            await ctx.send(f"✅ Bonne réponse, **{ctx.author.display_name}** !")
            # Update scores and XP
            scores = core.load_scores()
            uid = str(ctx.author.id)
            scores[uid] = scores.get(uid, 0) + 1
            core.save_scores(scores)
            xp_amount = 5 if difficulty == "easy" else 10 if difficulty == "normal" else 15
            core.add_xp(ctx.author.id, xp_amount)
            # Record mini-game participation
            core.add_mini_score(ctx.author.id, "animequiz", 1)
        else:
            await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title']['romaji']}**.")

    @commands.command(name="animequizmulti")
    async def animequizmulti(self, ctx: commands.Context, nb_questions: int = 5) -> None:
        """Lance un quiz multi questions (1 à 20).

        Les difficultés sont choisies au hasard et un récapitulatif est envoyé à la fin.
        """
        if nb_questions < 1 or nb_questions > 20:
            await ctx.send("❌ Tu dois choisir un nombre entre 1 et 20.")
            return
        await ctx.send(f"🎮 Lancement de **{nb_questions} questions** pour **{ctx.author.display_name}**...")
        difficulties = ["easy", "normal", "hard"]
        score = 0
        total_xp = 0
        for i in range(nb_questions):
            difficulty = random.choice(difficulties)
            sort_option = {
                "easy": "POPULARITY_DESC",
                "normal": "SCORE_DESC",
                "hard": "TRENDING_DESC",
            }[difficulty]
            anime = await self._get_random_anime(sort_option)
            if not anime:
                await ctx.send("❌ Impossible de récupérer un anime.")
                continue
            correct_titles = core.title_variants(anime["title"])
            image = anime.get("coverImage", {}).get("extraLarge") or anime.get("coverImage", {}).get("large")
            embed = discord.Embed(
                title=f"❓ Question {i+1}/{nb_questions} — difficulté `{difficulty}`",
                description="Tu as **20 secondes** pour deviner. Tape `jsp` pour passer.",
                color=discord.Color.orange(),
            )
            if image:
                embed.set_image(url=image)
            await ctx.send(embed=embed)
            def check(m: discord.Message) -> bool:
                return m.author == ctx.author and m.channel == ctx.channel
            try:
                msg = await self.bot.wait_for("message", timeout=20.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! C’était **{anime['title']['romaji']}**.")
                await asyncio.sleep(1.5)
                continue
            guess = core.normalize(msg.content)
            if guess == "jsp":
                await ctx.send(f"⏭️ Passé. C’était **{anime['title']['romaji']}**.")
            elif guess in correct_titles:
                await ctx.send("✅ Bonne réponse !")
                score += 1
                xp_gain = 5 if difficulty == "easy" else 10 if difficulty == "normal" else 15
                total_xp += xp_gain
                # Record mini-game score for each correct answer
                core.add_mini_score(ctx.author.id, "animequiz", 1)
            else:
                await ctx.send(f"❌ Faux ! C’était **{anime['title']['romaji']}**.")
            await asyncio.sleep(1.5)
        # Final results
        scores = core.load_scores()
        uid = str(ctx.author.id)
        # Penalty if less than half correct
        if score < (nb_questions / 2):
            penalty = 1
            scores[uid] = max(0, scores.get(uid, 0) - penalty)
            await ctx.send(f"⚠️ Tu as fait moins de 50% de bonnes réponses, -{penalty} point retiré.")
        else:
            scores[uid] = scores.get(uid, 0) + score
        core.save_scores(scores)
        core.add_xp(ctx.author.id, total_xp)
        await ctx.send(f"🏁 Fin du quiz ! Score final : **{score}/{nb_questions}** – 🎖️ XP gagné : **{total_xp}**")

    @commands.command(name="duel")
    async def duel(self, ctx: commands.Context, opponent: discord.Member) -> None:
        """Affronte un ami en duel de 3 questions."""
        if opponent.bot:
            await ctx.send("🤖 Tu ne peux pas défier un bot.")
            return
        if opponent == ctx.author:
            await ctx.send("🙃 Tu ne peux pas te défier toi-même.")
            return
        await ctx.send(f"⚔️ Duel entre **{ctx.author.display_name}** et **{opponent.display_name}** lancé !")
        players = [ctx.author, opponent]
        scores = {ctx.author.id: 0, opponent.id: 0}
        difficulties = ["easy", "normal", "hard"]
        for i in range(3):
            await ctx.send(f"❓ Question {i+1}/3...")
            difficulty = random.choice(difficulties)
            sort_option = {
                "easy": "POPULARITY_DESC",
                "normal": "SCORE_DESC",
                "hard": "TRENDING_DESC",
            }[difficulty]
            anime = await self._get_random_anime(sort_option)
            if not anime:
                await ctx.send("❌ Impossible de récupérer un anime.")
                continue
            correct_titles = core.title_variants(anime["title"])
            embed = discord.Embed(
                title=f"🎮 Duel – Question {i+1}/3",
                description="**Tu as 15 secondes** pour deviner l’anime. Tape `jsp` pour passer.",
                color=discord.Color.red(),
            )
            image = anime.get("coverImage", {}).get("extraLarge") or anime.get("coverImage", {}).get("large")
            if image:
                embed.set_image(url=image)
            await ctx.send(embed=embed)
            def check(m: discord.Message) -> bool:
                return m.channel == ctx.channel and m.author in players
            try:
                msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! C’était **{anime['title']['romaji']}**.")
                await asyncio.sleep(1)
                continue
            content = core.normalize(msg.content)
            if content == "jsp":
                await ctx.send(f"⏭️ Question passée. C’était **{anime['title']['romaji']}**.")
            elif content in correct_titles:
                scores[msg.author.id] += 1
                await ctx.send(f"✅ Bonne réponse de **{msg.author.display_name}** !")
            else:
                await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title']['romaji']}**.")
            await asyncio.sleep(1)
        # Determine winner
        s1, s2 = scores[ctx.author.id], scores[opponent.id]
        if s1 == s2:
            result = f"🤝 Égalité parfaite : {s1} - {s2}"
        else:
            winner = ctx.author if s1 > s2 else opponent
            loser = opponent if winner == ctx.author else ctx.author
            result = f"🏆 Victoire de **{winner.display_name}** ({s1} - {s2})"
            core.add_xp(winner.id, 20)
            # Record duel win in mini-game scores
            core.add_mini_score(winner.id, "duel", 1)
        await ctx.send(result)

    @commands.command(name="quiztop")
    async def quiztop(self, ctx: commands.Context) -> None:
        """Affiche le top 10 des scores du quiz."""
        scores = core.load_scores()
        if not scores:
            await ctx.send("🏆 Aucun score enregistré pour l’instant.")
            return
        # Prepare leaderboard (top 10)
        leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        lines = []
        for i, (uid, score) in enumerate(leaderboard, 1):
            try:
                user = await self.bot.fetch_user(int(uid))
                lines.append(f"{i}. **{user.display_name}** — {score} pts (Titre : {core.get_title_for_level(score)})")
            except Exception:
                continue
        desc = "\n".join(lines)
        # Load last month's winner from file
        winner_data = core.load_json(core.WINNER_FILE, None)
        winner_text = ""
        if winner_data:
            try:
                winner_user = await self.bot.fetch_user(int(winner_data.get("uid")))
                won_at = datetime.fromisoformat(winner_data.get("timestamp"))
                month = won_at.strftime("%B %Y")
                winner_text = f"🥇 Vainqueur {month} : **{winner_user.display_name}**"
            except Exception:
                pass
        # Countdown to next reset
        now = datetime.now(tz=core.TIMEZONE)
        if now.month == 12:
            next_month_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month_start = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        delta = next_month_start - now
        days_left = delta.days
        hours_left = delta.seconds // 3600
        countdown_text = f"⏳ Réinitialisation dans {days_left} jour(s) et {hours_left} heure(s)"
        embed = discord.Embed(
            title="🏆 Classement Anime Quiz",
            description=desc or "Aucun score.",
            color=discord.Color.gold(),
        )
        # Add countdown and last winner if available
        embed.add_field(name="Temps restant", value=countdown_text, inline=False)
        if winner_text:
            embed.add_field(name="Vainqueur du mois précédent", value=winner_text, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def myrank(self, ctx: commands.Context) -> None:
        """Affiche ton rang, ton XP et ton titre."""
        levels = core.load_levels()
        user_data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
        xp = user_data["xp"]
        level = user_data["level"]
        next_xp = (level + 1) * 100
        bar = core.get_xp_bar(xp, next_xp)
        embed = discord.Embed(
            title=f"🏅 Rang de {ctx.author.display_name}",
            color=discord.Color.purple(),
        )
        embed.add_field(
            name="🎮 Niveau & XP",
            value=f"Lv. {level} – {xp}/{next_xp} XP\n`{bar}`\nTitre : **{core.get_title_for_level(level)}**",
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quiz(bot))
