import discord
from discord.ext import commands
import random
import asyncio
import os

from modules import anilist, history_data, score_manager

class GuessGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_valid_guess(self, message, ctx):
        return (
            message.author == ctx.author
            and message.channel == ctx.channel
            and message.content.isdigit()
        )

    async def ask_question(self, ctx, title, question, options, correct_index, score_type, score_value=5):
        embed = discord.Embed(
            title=title,
            description=question,
            color=discord.Color.green()
        )
        for i, option in enumerate(options):
            embed.add_field(name=f"{i+1}️⃣", value=str(option), inline=False)

        await ctx.send(embed=embed)

        try:
            response = await self.bot.wait_for("message", timeout=20.0, check=lambda m: self.is_valid_guess(m, ctx))
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{options[correct_index]}**.")
            return

        choice = int(response.content) - 1
        if choice == correct_index:
            await ctx.send(f"✅ Bonne réponse ! +{score_value} points !")
            score_manager.update_guess_score(str(ctx.author.id), score_type, score_value)
        else:
            await ctx.send(f"❌ Mauvaise réponse ! C'était : **{options[correct_index]}**.")

    @commands.command(name="guessyear")
    async def guess_year(self, ctx):
        user_id = str(ctx.author.id)
        anime = anilist.get_random_anime(exclude_ids=history_data.get_recent_history(user_id))
        if not anime or not anime.get("startDate", {}).get("year"):
            await ctx.send("❌ Impossible de récupérer un anime avec une année valide.")
            return

        year = anime["startDate"]["year"]
        title = anime["title"]["romaji"]
        history_data.add_to_history(user_id, anime["id"])

        choices = [year]
        while len(choices) < 4:
            rand_year = random.randint(1980, 2023)
            if rand_year not in choices:
                choices.append(rand_year)
        random.shuffle(choices)

        await self.ask_question(
            ctx,
            title="📆 Guess the Year!",
            question=f"En quelle année est sorti **{title}** ?",
            options=choices,
            correct_index=choices.index(year),
            score_type="guessyear"
        )

    @commands.command(name="guessgenre")
    async def guess_genre(self, ctx):
        user_id = str(ctx.author.id)
        anime = anilist.get_random_anime(exclude_ids=history_data.get_recent_history(user_id))
        if not anime or not anime.get("genres"):
            await ctx.send("❌ Impossible de récupérer un anime avec des genres valides.")
            return

        genre = random.choice(anime["genres"])
        title = anime["title"]["romaji"]
        history_data.add_to_history(user_id, anime["id"])

        all_genres = anilist.get_all_genres()
        options = [genre]
        while len(options) < 4:
            g = random.choice(all_genres)
            if g not in options:
                options.append(g)
        random.shuffle(options)

        await self.ask_question(
            ctx,
            title="🎭 Guess the Genre!",
            question=f"Quel est un genre de l'anime **{title}** ?",
            options=options,
            correct_index=options.index(genre),
            score_type="guessgenre"
        )

    @commands.command(name="guessepisode")
    async def guess_episode(self, ctx):
        user_id = str(ctx.author.id)
        anime = anilist.get_random_anime(exclude_ids=history_data.get_recent_history(user_id))
        if not anime or not anime.get("episodes") or anime["episodes"] is None:
            await ctx.send("❌ Impossible de récupérer un anime avec un nombre d'épisodes valide.")
            return

        episodes = anime["episodes"]
        title = anime["title"]["romaji"]
        history_data.add_to_history(user_id, anime["id"])

        choices = [episodes]
        while len(choices) < 4:
            e = random.randint(4, 100)
            if e not in choices:
                choices.append(e)
        random.shuffle(choices)

        await self.ask_question(
            ctx,
            title="📺 Guess the Episodes!",
            question=f"Combien d’épisodes contient **{title}** ?",
            options=choices,
            correct_index=choices.index(episodes),
            score_type="guessepisode"
        )
      
    @commands.command(name="guesscharacter")
    async def guess_character(self, ctx):
        characters = anilist.get_random_characters(4)
        if not characters or len(characters) < 4:
            await ctx.send("❌ Impossible de récupérer les personnages.")
            return

        correct = random.choice(characters)
        correct_name = correct["name"]["full"]
        correct_image = correct["image"]["large"]
        options = [c["name"]["full"] for c in characters]
        correct_index = options.index(correct_name)

        embed = discord.Embed(
            title="👤 Guess the Character!",
            description="Quel est le nom de ce personnage ?",
            color=discord.Color.blurple()
        )
        embed.set_image(url=correct_image)
        for i, opt in enumerate(options):
            embed.add_field(name=f"{i+1}️⃣", value=opt, inline=False)

        await ctx.send(embed=embed)

        try:
            msg = await self.bot.wait_for("message", timeout=20.0, check=lambda m: self.is_valid_guess(m, ctx))
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé ! Il s’agissait de **{correct_name}**.")
            return

        choice = int(msg.content) - 1
        if choice == correct_index:
            await ctx.send("✅ Bien joué ! +5 points pour `guesscharacter`")
            score_manager.update_guess_score(str(ctx.author.id), "guesscharacter", 5)
        else:
            await ctx.send(f"❌ Mauvaise réponse ! Il fallait répondre : **{correct_name}**.")
          
    @commands.command(name="guessop")
    async def guess_op(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("🔇 Tu dois être dans un salon vocal pour jouer à ce jeu.")
            return

        voice_channel = ctx.author.voice.channel
        audio_folder = "assets/audio/openings"

        if not os.path.exists(audio_folder):
            await ctx.send("❌ Aucun fichier audio trouvé pour ce jeu.")
            return

        files = [f for f in os.listdir(audio_folder) if f.endswith(".mp3")]
        if not files:
            await ctx.send("❌ Il n’y a aucun extrait MP3 dans le dossier `assets/audio/openings/`.")
            return

        selected_file = random.choice(files)
        correct_anime = selected_file.replace(".mp3", "")
        choices = [correct_anime]

        # Générer 3 titres aléatoires supplémentaires (faux)
        while len(choices) < 4:
            alt = anilist.get_random_title()
            if alt not in choices:
                choices.append(alt)

        random.shuffle(choices)
        correct_index = choices.index(correct_anime)

        # Connexion au vocal
        try:
            vc = await voice_channel.connect()
        except:
            await ctx.send("❌ Impossible de rejoindre le vocal.")
            return

        # Lecture du fichier audio avec FFmpeg
        audio_source = discord.FFmpegPCMAudio(os.path.join(audio_folder, selected_file))
        vc.play(audio_source)

        # Envoyer l'embed avec les choix
        embed = discord.Embed(
            title="🎵 Guess the Opening!",
            description="De quel anime vient cet opening ?",
            color=discord.Color.purple()
        )
        for i, title in enumerate(choices):
            embed.add_field(name=f"{i+1}️⃣", value=title, inline=False)

        await ctx.send(embed=embed)

        def check(m):
            return (
                m.author == ctx.author and
                m.channel == ctx.channel and
                m.content.isdigit()
            )

        try:
            msg = await self.bot.wait_for("message", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{correct_anime}**.")
            await vc.disconnect()
            return

        await vc.disconnect()

        choice = int(msg.content) - 1
        if choice == correct_index:
            await ctx.send("✅ Bonne réponse ! +5 points pour `guessop`")
            score_manager.update_guess_score(str(ctx.author.id), "guessop", 5)
        else:
            await ctx.send(f"❌ Mauvaise réponse ! C’était : **{correct_anime}**.")

async def setup(bot):
    await bot.add_cog(Guess(bot))

