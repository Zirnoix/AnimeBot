import asyncio
import random
from datetime import datetime
import discord
from discord.ext import commands

from restructured_bot.modules import core

class Minigames(commands.Cog):
    """Cog pour les mini-jeux de quiz et challenges."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx: commands.Context, difficulty: str = "normal") -> None:
        """Lance un quiz solo : deviner un anime à partir de son affiche."""
        await ctx.send("🎮 Préparation du quiz...")
        difficulty = difficulty.lower()
        sort_option = {
            "easy": "POPULARITY_DESC",
            "hard": "TRENDING_DESC"
        }.get(difficulty, "SCORE_DESC")
        anime = None
        # Requête AniList aléatoire
        for _ in range(10):
            page = random.randint(1, 500)
            query = f'''
            query {{
              Page(perPage: 1, page: {page}) {{
                media(type: ANIME, isAdult: false, sort: {sort_option}) {{
                  id
                  title {{ romaji english native }}
                  coverImage {{ large }}
                }}
              }}
            }}
            '''
            data = core.query_anilist(query)
            try:
                anime = data["data"]["Page"]["media"][0]
                break
            except Exception:
                continue
        if not anime:
            await ctx.send("❌ Aucun anime trouvé.")
            return
        # Titres acceptés (normalisés)
        romaji = anime["title"].get("romaji", "")
        english = anime["title"].get("english", "")
        native = anime["title"].get("native", "")
        correct_titles = {core.normalize(t) for t in [romaji, english, native] if t}
        # Envoyer l'embed de question avec l'image
        embed = discord.Embed(
            title="❓ Quel est cet anime ?",
            description="Tu as **20 secondes** pour deviner. Tape `jsp` si tu ne sais pas.",
            color=discord.Color.orange()
        )
        embed.set_image(url=anime["coverImage"]["large"])
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
            # Incrémenter le score et XP
            scores = core.load_scores()
            uid = str(ctx.author.id)
            scores[uid] = scores.get(uid, 0) + 1
            core.save_scores(scores)
            xp_gain = 10
            if difficulty == "easy":
                xp_gain = 5
            elif difficulty == "hard":
                xp_gain = 15
            core.add_xp(ctx.author.id, amount=xp_gain)
        else:
            await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title']['romaji']}**.")

    @commands.command(name="animequizmulti")
    async def anime_quiz_multi(self, ctx: commands.Context, nb_questions: int = 5) -> None:
        """Lance un quiz multi-questions (N questions aléatoires)."""
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
                "hard": "TRENDING_DESC"
            }[difficulty]
            anime = None
            for _ in range(10):
                page = random.randint(1, 500)
                query = f'''
                query {{
                  Page(perPage: 1, page: {page}) {{
                    media(type: ANIME, isAdult: false, sort: {sort_option}) {{
                      id
                      title {{ romaji english native }}
                      coverImage {{ large }}
                    }}
                  }}
                }}
                '''
                data = core.query_anilist(query)
                try:
                    anime = data["data"]["Page"]["media"][0]
                    break
                except Exception:
                    continue
            if not anime:
                await ctx.send("❌ Impossible de récupérer un anime.")
                continue
            correct_titles = {core.normalize(t) for t in [anime["title"].get("romaji",""), anime["title"].get("english",""), anime["title"].get("native","")] if t}
            image_url = anime["coverImage"]["large"]
            embed = discord.Embed(
                title=f"❓ Question {i+1}/{nb_questions} — difficulté `{difficulty}`",
                description="Tu as **20 secondes** pour deviner. Tape `jsp` pour passer.",
                color=discord.Color.orange()
            )
            embed.set_image(url=image_url)
            await ctx.send(embed=embed)
            def check(m: discord.Message) -> bool:
                return m.author == ctx.author and m.channel == ctx.channel
            try:
                msg = await self.bot.wait_for("message", timeout=20.0, check=check)
                guess = core.normalize(msg.content)
                if guess == "jsp":
                    await ctx.send(f"⏭️ Passé. C’était **{anime['title']['romaji']}**.")
                    continue
                if guess in correct_titles:
                    await ctx.send("✅ Bonne réponse !")
                    score += 1
                    xp_gain = 5 if difficulty == "easy" else 10 if difficulty == "normal" else 15
                    total_xp += xp_gain
                else:
                    await ctx.send(f"❌ Faux ! C’était **{anime['title']['romaji']}**.")
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! C’était **{anime['title']['romaji']}**.")
            await asyncio.sleep(1.5)
        # Mise à jour des scores globaux
        scores = core.load_scores()
        uid = str(ctx.author.id)
        # Pénalité si moins de 50% de bonnes réponses
        if score < (nb_questions // 2):
            penalty = 1
            scores[uid] = max(0, scores.get(uid, 0) - penalty)
            await ctx.send(f"⚠️ Tu as fait moins de 50% de bonnes réponses, -{penalty} point retiré.")
        else:
            scores[uid] = scores.get(uid, 0) + score
        core.save_scores(scores)
        core.add_xp(ctx.author.id, amount=total_xp)
        await ctx.send(f"🏁 Fin du quiz ! Score final : **{score}/{nb_questions}** – 🎖️ XP gagné : **{total_xp}**")

    @commands.command(name="duel")
    async def duel(self, ctx: commands.Context, opponent: discord.Member) -> None:
        """Organise un duel de quiz en 3 questions entre deux membres."""
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
        for i in range(1, 4):
            await ctx.send(f"❓ Question {i}/3...")
            difficulty = random.choice(difficulties)
            sort_option = {
                "easy": "POPULARITY_DESC",
                "normal": "SCORE_DESC",
                "hard": "TRENDING_DESC"
            }[difficulty]
            anime = None
            for _ in range(10):
                page = random.randint(1, 500)
                query = f'''
                query {{
                  Page(perPage: 1, page: {page}) {{
                    media(type: ANIME, isAdult: false, sort: {sort_option}) {{
                      id
                      title {{ romaji english native }}
                      coverImage {{ large }}
                    }}
                  }}
                }}
                '''
                data = core.query_anilist(query)
                try:
                    anime = data["data"]["Page"]["media"][0]
                    break
                except Exception:
                    continue
            if not anime:
                await ctx.send("❌ Impossible de récupérer un anime pour la question.")
                continue
            # Préparer les réponses acceptées
            romaji = anime["title"].get("romaji", "")
            english = anime["title"].get("english", "")
            native = anime["title"].get("native", "")
            correct_answers = {core.normalize(t) for t in [romaji, english, native] if t}
            # Envoyer l'image de l'anime en question
            embed = discord.Embed(
                title=f"🎮 Duel – Question {i}/3",
                description="**15 secondes** pour deviner l’anime. Tape `jsp` pour passer.",
                color=discord.Color.red()
            )
            embed.set_image(url=anime["coverImage"]["large"])
            await ctx.send(embed=embed)
            def check(m: discord.Message) -> bool:
                return m.channel == ctx.channel and m.author in players
            try:
                msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! C’était **{anime['title']['romaji']}**.")
                continue
            guess = core.normalize(msg.content)
            if guess == "jsp":
                await ctx.send(f"⏭️ Question passée. C’était **{anime['title']['romaji']}**.")
                continue
            if guess in correct_answers:
                scores[msg.author.id] += 1
                await ctx.send(f"✅ Bonne réponse de **{msg.author.display_name}** !")
            else:
                await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title']['romaji']}**.")
            await asyncio.sleep(1)
        # Résultat final
        s1, s2 = scores[ctx.author.id], scores[opponent.id]
        if s1 == s2:
            result = f"🤝 Égalité parfaite : {s1} - {s2}"
        else:
            winner = ctx.author if s1 > s2 else opponent
            loser = opponent if winner == ctx.author else ctx.author
            result = f"🏆 Victoire de **{winner.display_name}** ({s1} - {s2})"
            core.add_xp(winner.id, amount=20)
        await ctx.send(result)

    @commands.command(name="animebattle")
    async def anime_battle(self, ctx: commands.Context, opponent: discord.Member) -> None:
        """Duel de quiz en 3 questions basé sur des descriptions d'anime."""
        if opponent.bot:
            await ctx.send("❌ Tu dois défier un membre humain : `!animebattle @ami`")
            return
        if opponent == ctx.author:
            await ctx.send("🙃 Tu ne peux pas jouer seul dans ce mode.")
            return
        await ctx.send(f"🎮 Duel entre **{ctx.author.display_name}** et **{opponent.display_name}** lancé !")
        players = [ctx.author, opponent]
        scores = {ctx.author.id: 0, opponent.id: 0}
        for numero in range(1, 4):
            await ctx.send(f"❓ Question {numero}/3...")
            anime = None
            # Tirer un anime aléatoire (haut score)
            for _ in range(10):
                page = random.randint(1, 500)
                query = f'''
                query {{
                  Page(perPage: 1, page: {page}) {{
                    media(type: ANIME, isAdult: false, sort: SCORE_DESC) {{
                      id
                      title {{ romaji english native }}
                      description(asHtml: false)
                    }}
                  }}
                }}
                '''
                data = core.query_anilist(query)
                try:
                    anime = data["data"]["Page"]["media"][0]
                    break
                except Exception:
                    continue
            if not anime:
                await ctx.send("❌ Impossible de récupérer un anime pour la question.")
                return
            # Préparer la description (première phrase) et la traduire en français
            raw_desc = anime.get("description", "Pas de description.")
            raw_sentence = raw_desc.split(".")[0] + "."
            try:
                from deep_translator import GoogleTranslator
                desc_fr = GoogleTranslator(source='auto', target='fr').translate(raw_sentence)
            except Exception:
                desc_fr = raw_sentence  # Si échec, garder la description originale
            # Envoyer l'énoncé de la question
            embed = discord.Embed(
                title=f"🎲 Duel (description) – Question {numero}/3",
                description=f"**Description** : {desc_fr}\n\n*Devinez l’anime ! (15 sec, `jsp` pour passer)*",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            def check(m: discord.Message) -> bool:
                return m.channel == ctx.channel and m.author in players
            try:
                msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé. C’était **{anime['title']['romaji']}**.")
                continue
            guess = core.normalize(msg.content)
            if guess == "jsp":
                await ctx.send(f"⏭️ Passé. C’était **{anime['title']['romaji']}**.")
                continue
            # Titres acceptés
            titles = [anime["title"].get("romaji", ""), anime["title"].get("english", ""), anime["title"].get("native", "")]
            if guess in {core.normalize(t) for t in titles if t}:
                scores[msg.author.id] += 1
                await ctx.send(f"✅ **{msg.author.display_name}** a trouvé la bonne réponse !")
            else:
                await ctx.send(f"❌ Mauvaise réponse. C’était **{anime['title']['romaji']}**.")
        # Annoncer le vainqueur
        s1, s2 = scores[ctx.author.id], scores[opponent.id]
        if s1 == s2:
            await ctx.send(f"🤝 Égalité parfaite : {s1} - {s2}")
        else:
            winner = ctx.author if s1 > s2 else opponent
            core.add_xp(winner.id, amount=20)
            await ctx.send(f"🏆 **{winner.display_name}** remporte la victoire ! (Score final {s1} - {s2})")

    @commands.command(name="quiztop")
    async def quiz_top(self, ctx: commands.Context) -> None:
        """Affiche le classement des 10 meilleurs scores au quiz."""
        import calendar
        scores = core.load_scores()
        if not scores:
            await ctx.send("🏆 Aucun score enregistré pour l’instant.")
            return
        # Top 10 des scores
        leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        # Titre honorifique selon le score
        def get_title(score: int) -> str:
            titles = [
                (100, "👑 Dieu de l'Anime"),
                (95, "💫 Génie légendaire"),
                (90, "🔥 Maître incontesté"),
                (85, "🌟 Pro absolu"),
                (80, "🎯 Otaku ultime"),
                (75, "🎬 Cinéphile expert"),
                (70, "🧠 Stratège anime"),
                (65, "⚡ Analyste senior"),
                (60, "📺 Passionné confirmé"),
                (55, "🎮 Joueur fidèle"),
                (50, "📘 Fan régulier"),
                (45, "💡 Connaisseur"),
                (40, "📀 Binge-watcher"),
                (35, "🎵 Amateur éclairé"),
                (30, "🎙️ Apprenti curieux"),
                (25, "📚 Étudiant otaku"),
                (20, "📦 Débutant prometteur"),
                (15, "🌱 Petit curieux"),
                (10, "🍼 Nouveau joueur"),
                (5,  "🔰 Padawan"),
                (0,  "🐣 Nouvel arrivant")
            ]
            for threshold, title in titles:
                if score >= threshold:
                    return title
            return "❓ Inconnu"
        desc = ""
        for i, (uid, score) in enumerate(leaderboard, start=1):
            try:
                user = await self.bot.fetch_user(int(uid))
                title = get_title(score)
                desc += f"{i}. **{user.display_name}** — {score} pts {title}\n"
            except Exception:
                continue
        embed = discord.Embed(title="🏆 Classement Anime Quiz", description=desc, color=discord.Color.gold())
        # Jours restants avant réinitialisation mensuelle
        now = datetime.now(tz=core.TIMEZONE)
        _, last_day = calendar.monthrange(now.year, now.month)
        reset_date = datetime(now.year, now.month, last_day, 23, 59, tzinfo=core.TIMEZONE)
        remaining = reset_date - now
        days_left = remaining.days + 1
        embed.set_footer(text=f"⏳ Réinitialisation dans {days_left} jour(s)")
        # Vainqueur du mois précédent si disponible
        winner_data = core.load_json(core.WINNER_FILE, {})
        if winner_data.get("uid"):
            try:
                prev_user = await self.bot.fetch_user(int(winner_data["uid"]))
                embed.add_field(
                    name="🥇 Vainqueur du mois dernier",
                    value=f"**{prev_user.display_name}**",
                    inline=False
                )
            except Exception:
                pass
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def my_rank(self, ctx: commands.Context) -> None:
        """Affiche votre niveau actuel, XP et titre honorifique."""
        levels = core.load_levels()
        data = levels.get(str(ctx.author.id), {"xp": 0, "level": 0})
        level = data["level"]
        xp = data["xp"]
        next_xp = (level + 1) * 100
        bar = core.get_xp_bar(xp, next_xp)
        title = core.get_title_for_level(level)
        embed = discord.Embed(title=f"🏅 Rang de {ctx.author.display_name}", color=discord.Color.purple())
        embed.add_field(
            name="🎮 Niveau & XP",
            value=f"Niveau {level} – {xp}/{next_xp} XP\n`{bar}`\nTitre : **{title}**",
            inline=False
        )
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Minigames(bot))
