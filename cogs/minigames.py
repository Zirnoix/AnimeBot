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
from modules.voice import play_clip_in_channel

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
        """Devine l'opening d'un anime (quiz multi-joueurs, 30s, podium de rapidité)."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("🔇 Tu dois être dans un **salon vocal** pour jouer.")

        voice_channel = ctx.author.voice.channel
        audio_folder = "assets/audio/openings"

        if not os.path.exists(audio_folder):
            return await ctx.send("❌ Le dossier des openings n'est pas configuré.")
        files = [f for f in os.listdir(audio_folder) if f.endswith(".mp3")]
        if not files:
            return await ctx.send("❌ Aucun opening trouvé dans le dossier.")

        selected_file = random.choice(files)
        filepath = os.path.join(audio_folder, selected_file)
        correct_anime = os.path.splitext(selected_file)[0]

        # 4 choix : bonne réponse + 3 leurres depuis AniList
        query = '''
        query {
          Page(perPage: 25) {
            media(type: ANIME, sort: POPULARITY_DESC) {
              title { romaji }
            }
          }
        }
        '''
        try:
            data = core.query_anilist(query)
            pool = [m["title"]["romaji"] for m in data["data"]["Page"]["media"]]
        except Exception:
            pool = []

        choices = [correct_anime]
        while len(choices) < 4 and pool:
            alt = random.choice(pool)
            if alt not in choices:
                choices.append(alt)
        # si AniList HS, complète avec des placeholders pour éviter le crash
        while len(choices) < 4:
            choices.append(f"Option {len(choices)+1}")

        random.shuffle(choices)
        correct_index = choices.index(correct_anime)

        # Lance l’audio (20s) et pose la question
        asyncio.create_task(
            play_clip_in_channel(voice_channel, filepath, duration_sec=20, disconnect_after=True)
        )

        question = discord.Embed(
            title="🎵 Devine l’opening !",
            description="De quel anime vient cet opening ?\nRéponds par `1`, `2`, `3` ou `4`. (30s)",
            color=discord.Color.purple(),
        )
        for i, title in enumerate(choices, 1):
            question.add_field(name=f"{i}️⃣", value=title, inline=False)
        await ctx.send(embed=question)

        # Collecte des réponses pendant 30s
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 30

        winners_order: list[discord.Member] = []      # top 3 en ordre d’arrivée
        others_correct: list[discord.Member] = []     # les autres qui ont bon avant la fin
        already_answered: set[int] = set()            # 1 réponse par joueur (empêche le spam)

        def check(m: discord.Message) -> bool:
            if m.author.bot:
                return False
            if m.channel != ctx.channel:
                return False
            if not (m.content.isdigit() and 1 <= int(m.content) <= 4):
                return False
            # doit être dans le même salon vocal
            if not m.author.voice or m.author.voice.channel != voice_channel:
                return False
            # une seule tentative par joueur
            if m.author.id in already_answered:
                return False
            return True

        # boucle d’attente non bloquante
        while True:
            timeout = deadline - loop.time()
            if timeout <= 0:
                break
            try:
                msg = await self.bot.wait_for("message", timeout=timeout, check=check)
            except asyncio.TimeoutError:
                break

            already_answered.add(msg.author.id)
            choice = int(msg.content) - 1
            if choice == correct_index:
                # classements : 1er -> winners_order[0], 2e -> [1], 3e -> [2]
                if len(winners_order) < 3:
                    winners_order.append(msg.author)
                    await ctx.send(f"✅ Bonne réponse, {msg.author.mention} !")
                else:
                    # au-delà du top 3, on note quand même les bons
                    others_correct.append(msg.author)
            else:
                await ctx.send(f"❌ Mauvaise réponse, {msg.author.mention}.")

        # Attribution des récompenses
        if not winners_order and not others_correct:
            return await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{correct_anime}**")

        # Barème d’XP (modifie si tu veux)
        podium_xp = [15, 10, 7]  # 1er, 2e, 3e
        others_xp = 3            # tous les autres corrects dans le temps

        # Donne de l’XP et incrémente le mini-score à tous ceux qui ont bien répondu
        # (si tu préfères ne l'ajouter qu’aux 3 premiers, change la boucle ci-dessous)
        award_lines = []
        for rank, user in enumerate(winners_order, start=1):
            xp = podium_xp[rank - 1]
            award_lines.append(f"**#{rank}** {user.mention} — +{xp} XP")
            try:
                await core.add_xp(self.bot, ctx.channel, user.id, xp)
            except Exception:
                pass
            try:
                core.add_mini_score(user.id, "guessop", 1)
            except Exception:
                pass

        for user in others_correct:
            award_lines.append(f"• {user.mention} — +{others_xp} XP")
            try:
                await core.add_xp(self.bot, ctx.channel, user.id, others_xp)
            except Exception:
                pass
            try:
                core.add_mini_score(user.id, "guessop", 1)
            except Exception:
                pass

        # Résumé final
        result = discord.Embed(
            title="🏁 Résultats — Guess OP",
            description=f"✅ **Réponse :** {correct_anime}",
            color=discord.Color.gold(),
        )
        if award_lines:
            result.add_field(name="Récompenses", value="\n".join(award_lines), inline=False)
        await ctx.send(embed=result)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiniGames(bot))
