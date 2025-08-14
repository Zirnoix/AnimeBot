"""
Mini‑games commands.

This cog regroupe plusieurs petits jeux pour divertir les utilisateurs :
* **Higher/Lower** : devinez quel anime est le plus populaire.
* **Guess Year** : devinez l'année de diffusion d'un anime.
* **Higher Mean** : devinez quelle série a la meilleure note moyenne.
* **Guess Episodes** : devinez le nombre d'épisodes d'une série.
* **Guess Genre** : trouvez un des genres principaux d'un anime.
* **Guess Character** : devinez le nom d'un personnage.
* **Guess Opening** : identifiez l'opening d'un anime.
"""

from __future__ import annotations
import aiohttp
from PIL import Image
from io import BytesIO
import random
import asyncio
import os
from typing import Optional
from discord.ui import View, Button
import discord
from discord.ext import commands
from modules import core

class HigherLowerView(View):
    def __init__(self, ctx, choice1, choice2):
        super().__init__(timeout=20)
        self.ctx = ctx
        self.choice1 = choice1
        self.choice2 = choice2
        self.result_sent = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ Ce mini‑jeu n’est pas pour toi.", ephemeral=True)
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

        if answer == correct:
            await interaction.response.send_message(
                f"✅ Bravo ! **{self.choice1['title']['romaji']}** ({pop1}) vs **{self.choice2['title']['romaji']}** ({pop2})\nTu gagnes **5 XP** !"
            )
            await core.add_xp(interaction.client, interaction.channel, interaction.user.id, 5)
            core.add_mini_score(interaction.user.id, "higherlower", 1)  # <-- plus de self.ctx
        else:
            await interaction.response.send_message(
                f"❌ Mauvais choix. **{self.choice1['title']['romaji']}** : {pop1}, **{self.choice2['title']['romaji']}** : {pop2}."
            )
        self.stop()

class MiniGames(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="higherlower")
    async def higher_lower(self, ctx: commands.Context):
        await ctx.send("🎲 Préparation du mini‑jeu…")

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
        data = core.query_anilist(query, {"page": page})
        if not data or not data.get("data"):
            await ctx.send("❌ Impossible de récupérer des données pour le mini‑jeu.")
            return

        media_list = data["data"]["Page"]["media"]
        if len(media_list) < 2:
            await ctx.send("❌ Pas assez de données pour jouer.")
            return

        choice1, choice2 = random.sample(media_list, 2)

        embed = discord.Embed(
            title="⬆️⬇️ Quel anime est le plus populaire ?",
            description=(
                "Clique sur **1️⃣** ou **2️⃣** pour choisir :\n\n"
                "**1️⃣** {a1}\n"
                "**2️⃣** {a2}"
            ).format(a1=choice1["title"]["romaji"], a2=choice2["title"]["romaji"]),
            color=discord.Color.orange(),
        )
        # Récupération des deux images
        url1 = choice1["coverImage"]["extraLarge"]
        url2 = choice2["coverImage"]["extraLarge"]

        async with aiohttp.ClientSession() as session:
            async with session.get(url1) as resp1:
                img1_bytes = await resp1.read()
            async with session.get(url2) as resp2:
                img2_bytes = await resp2.read()

        img1 = Image.open(BytesIO(img1_bytes)).convert("RGBA")
        img2 = Image.open(BytesIO(img2_bytes)).convert("RGBA")

        # Redimensionne les deux images à même hauteur
        max_height = max(img1.height, img2.height)
        img1 = img1.resize((int(img1.width * max_height / img1.height), max_height))
        img2 = img2.resize((int(img2.width * max_height / img2.height), max_height))

        # Ajoute une séparation verticale de 10px
        separator_width = 10
        total_width = img1.width + img2.width + separator_width
        combined = Image.new("RGBA", (total_width, max_height), (0, 0, 0, 255))  # fond noir

        # Colle img1, la séparation, puis img2
        combined.paste(img1, (0, 0))
        # Rien à faire pour la séparation, elle est déjà noire
        combined.paste(img2, (img1.width + separator_width, 0))

        # Convertit et envoie
        buffer = BytesIO()
        combined.save(buffer, format="PNG")
        buffer.seek(0)
        file = discord.File(buffer, filename="duel.png")

        embed.set_image(url="attachment://duel.png")
        view = HigherLowerView(ctx, choice1, choice2)
        await ctx.send(embed=embed, view=view, file=file)


        try:
            await view.wait()
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé !")

    @commands.command(name="guessyear")
    async def guess_year(self, ctx: commands.Context) -> None:
        """Devine l'année de diffusion d'un anime au hasard."""
        await ctx.send("🗓️ Chargement d'un anime…")
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
        data = core.query_anilist(query, {"page": page})
        try:
            anime = data["data"]["Page"]["media"][0]
            title = anime["title"]["romaji"]
            year = anime.get("startDate", {}).get("year")
            if not year:
                await ctx.send("❌ L'année de cet anime est indisponible.")
                return

            embed = discord.Embed(
                title="📅 Mini‑jeu : Devine l'année !",
                description=(
                    f"En quelle année **{title}** a‑t‑il commencé à être diffusé ?\n"
                    "Réponds par une année (ex : `2015`)."
                ),
                color=discord.Color.purple(),
            )
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
                    await ctx.send(f"✅ Bravo ! L'année était bien **{year}** (tu as répondu {guessed_year}). Tu gagnes 8 XP !")
                    await core.add_xp(self.bot, ctx.channel, ctx.author.id, 8)
                    core.add_mini_score(ctx.author.id, "guessyear", 1)
                else:
                    await ctx.send(f"❌ Raté. L'année était **{year}** (tu as répondu {guessed_year}).")
            except ValueError:
                await ctx.send(f"❌ Format invalide. L'année était **{year}**.")
        except (Exception, asyncio.TimeoutError):
            await ctx.send("❌ Une erreur s'est produite ou temps écoulé.")


    @commands.command(name="guessepisodes")
    async def guess_episodes(self, ctx: commands.Context) -> None:
        """Devine le nombre d'épisodes d'un anime."""
        await ctx.send("🎬 Sélection d'un anime…")
        anime = None
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
            data = core.query_anilist(query, {"page": page})
            try:
                candidate = data["data"]["Page"]["media"][0]
                if candidate.get("episodes") and isinstance(candidate.get("episodes"), int):
                    anime = candidate
                    break
            except Exception:
                continue

        if not anime:
            await ctx.send("❌ Impossible de récupérer un anime avec un nombre d'épisodes connu.")
            return

        title = anime["title"]["romaji"]
        episodes = anime["episodes"]
        embed = discord.Embed(
            title="🎞️ Mini‑jeu : Combien d'épisodes ?",
            description=(
                f"Combien d'épisodes compte **{title}** ?\n"
                "Réponds par un nombre (ex : `24`)."
            ),
            color=discord.Color.blue(),
        )
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
                    await ctx.send(f"✅ Bravo ! **{title}** compte {episodes} épisodes (tu as répondu {guessed}). Tu gagnes 8 XP !")
                    await core.add_xp(self.bot, ctx.channel, ctx.author.id, 8)
                    core.add_mini_score(ctx.author.id, "guessepisodes", 1)
                else:
                    await ctx.send(f"❌ Raté. **{title}** compte {episodes} épisodes (tu as répondu {guessed}).")
            except ValueError:
                await ctx.send(f"❌ Ce n'est pas un nombre valide. **{title}** a **{episodes}** épisodes.")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé ! Le mini‑jeu est annulé.")

    @commands.command(name="guessgenre")
    async def guess_genre(self, ctx: commands.Context) -> None:
        """Devine un des genres d'un anime."""
        await ctx.send("🎭 Sélection d'un anime…")
        anime = None
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
            data = core.query_anilist(query, {"page": page})
            try:
                candidate = data["data"]["Page"]["media"][0]
                if candidate.get("genres"):
                    anime = candidate
                    break
            except Exception:
                continue

        if not anime:
            await ctx.send("❌ Impossible de récupérer un anime avec des genres.")
            return

        title = anime["title"]["romaji"]
        genres = [g.lower() for g in anime.get("genres", [])]
        embed = discord.Embed(
            title="🎭 Mini‑jeu : Devine le genre !",
            description=(
                f"Quel est un des genres de **{title}** ?\n"
                "Réponds par un genre (ex : `Action`, `Romance`)."
            ),
            color=discord.Color.magenta(),
        )
        img_url = anime.get("coverImage", {}).get("extraLarge")
        if img_url:
            embed.set_image(url=img_url)
        await ctx.send(embed=embed)

        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for("message", timeout=20.0, check=check)
            guess = msg.content.strip().lower()
            if guess in [g.lower() for g in genres]:
                await ctx.send(f"✅ Exact ! Les genres de **{title}** incluent {', '.join(anime['genres'])}. Tu gagnes 5 XP !")
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, 5)
                core.add_mini_score(ctx.author.id, "guessgenre", 1)
            else:
                await ctx.send(f"❌ Mauvaise réponse. Les genres de **{title}** étaient : {', '.join(anime['genres'])}.")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé ! Le mini‑jeu est annulé.")

    @commands.command(name="guesscharacter")
    async def guess_character(self, ctx: commands.Context) -> None:
        """Devine le personnage d'anime affiché (avec boutons)."""
        page = random.randint(1, 100)
        query = '''
        query ($page: Int) {
          Page(page: $page, perPage: 4) {
            characters(sort: FAVOURITES_DESC) {
              name { full }
              image { large }
              media(type: ANIME) {
                nodes {
                  title { romaji }
                }
              }
            }
          }
        }
        '''
        data = core.query_anilist(query, {"page": page})
        if not data or "data" not in data:
            await ctx.send("❌ Impossible de récupérer les personnages.")
            return

        characters = data["data"]["Page"]["characters"]
        if len(characters) < 4:
            await ctx.send("❌ Pas assez de personnages trouvés.")
            return

        correct = random.choice(characters)
        correct_name = correct["name"]["full"]
        correct_image = correct["image"]["large"]
        options = [c["name"]["full"] for c in characters]
        correct_index = options.index(correct_name)

        embed = discord.Embed(
            title="👤 Devine le personnage !",
            description="Clique sur le bouton correspondant au bon nom.",
            color=discord.Color.blurple()
        )
        embed.set_image(url=correct_image)

        # Vue avec boutons
        view = View(timeout=20)
    
        async def make_button_callback(interaction, index):
            if interaction.user != ctx.author:
                await interaction.response.send_message("❌ Ce n'est pas ton quiz !", ephemeral=True)
                return

            if index == correct_index:
                await interaction.response.edit_message(content="✅ Bien joué ! Tu gagnes 5 XP !", view=None)
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, 5)
                core.add_mini_score(ctx.author.id, "guesscharacter", 1)
            else:
                await interaction.response.edit_message(content=f"❌ Mauvaise réponse ! C'était : **{correct_name}**", view=None)

        # Création des boutons
        for i, opt in enumerate(options):
            btn = Button(label=opt, style=discord.ButtonStyle.primary)
            btn.callback = lambda interaction, idx=i: make_button_callback(interaction, idx)
            view.add_item(btn)

        await ctx.send(embed=embed, view=view)

@commands.command(name="guessop")
async def guess_op(self, ctx: commands.Context) -> None:
    """Devine l'opening d'un anime."""
    # Vérification de la présence en vocal
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("🔇 Tu dois être dans un salon vocal pour jouer à ce jeu.")
        return

    voice_channel = ctx.author.voice.channel
    audio_folder = "assets/audio/openings"

    if not os.path.exists(audio_folder):
        await ctx.send("❌ Le dossier des openings n'est pas configuré.")
        return

    files = [f for f in os.listdir(audio_folder) if f.endswith(".mp3")]
    if not files:
        await ctx.send("❌ Aucun opening trouvé dans le dossier.")
        return

    selected_file = random.choice(files)
    correct_anime = selected_file.replace(".mp3", "")

    # Préparation de la liste de choix (1 bonne réponse + 3 leurres aléatoires)
    query = '''
    query {
      Page(perPage: 10) {
        media(type: ANIME, sort: POPULARITY_DESC) {
          title { romaji }
        }
      }
    }
    '''
    try:
        data = core.query_anilist(query)
        anime_titles = [m["title"]["romaji"] for m in data["data"]["Page"]["media"]]
        choices = [correct_anime]
        while len(choices) < 4:
            alt = random.choice(anime_titles)
            if alt not in choices:
                choices.append(alt)
        random.shuffle(choices)
        correct_index = choices.index(correct_anime)

        # Connexion au salon vocal et lecture de l'extrait audio (20 secondes)
        vc = await voice_channel.connect()
        audio_source = discord.FFmpegPCMAudio(
            os.path.join(audio_folder, selected_file),
            executable="ffmpeg",
            before_options="-t 20",  # limite la lecture à 20s
            options="-vn"            # ignore la vidéo le cas échéant, audio only
        )
        vc.play(audio_source)

        # Envoi de l'embed avec les choix
        embed = discord.Embed(
            title="🎵 Devine l'opening !",
            description="De quel anime vient cet opening ?",
            color=discord.Color.purple()
        )
        for i, title in enumerate(choices, 1):
            embed.add_field(name=f"{i}️⃣", value=title, inline=False)
        await ctx.send(embed=embed)

        # Nouvelle fonction de vérification : n'importe quel utilisateur du vocal peut répondre
        def check(m: discord.Message) -> bool:
            return (
                m.channel == ctx.channel
                and m.content.isdigit()
                and 1 <= int(m.content) <= 4
                and not m.author.bot
                and m.author.voice  # l'auteur a une connexion vocal...
                and m.author.voice.channel == voice_channel  # ... dans le même salon vocal
            )

        winner = None
        # Temps limite de 30 secondes pour répondre
        end_time = asyncio.get_running_loop().time() + 30  # ou +20 pour 20 secondes
        while True:
            # Calcule le temps restant à chaque itération
            timeout = end_time - asyncio.get_running_loop().time()
            if timeout <= 0:
                break  # temps écoulé
            try:
                msg = await self.bot.wait_for("message", timeout=timeout, check=check)
            except asyncio.TimeoutError:
                break  # fin du timer sans réponse correcte
            # Une réponse valide a été reçue
            choice = int(msg.content) - 1
            if choice == correct_index:
                # Bonne réponse trouvée
                winner = msg.author
                vc.stop()  # stoppe la lecture audio immédiatement
                await ctx.send(f"✅ Bonne réponse, {msg.author.mention} ! Tu gagnes 15 XP !")
                await core.add_xp(self.bot, ctx.channel, msg.author.id, 15)
                core.add_mini_score(msg.author.id, "guessop", 1)
                break  # on sort de la boucle, le quiz est terminé
            else:
                # Mauvaise réponse -> on informe et on continue à attendre d'autres propositions
                await ctx.send(f"❌ Mauvaise réponse, {msg.author.mention} !")
                # (Le joueur peut éventuellement réessayer, ou laisser quelqu'un d'autre répondre)
                continue

        # Si la boucle se termine sans vainqueur, notifier la bonne réponse
        if winner is None:
            vc.stop()  # on arrête l'audio si ce n'est pas déjà fini
            await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{correct_anime}**")

    except Exception as e:
        await ctx.send("❌ Une erreur s'est produite.")

    finally:
        # Déconnexion du salon vocal quoiqu'il arrive
        try:
            await vc.disconnect()
        except:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiniGames(bot))
