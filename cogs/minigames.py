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

import random
import asyncio
import os
from typing import Optional

import discord
from discord.ext import commands

from modules import core


class MiniGames(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="higherlower")
    async def higher_lower(self, ctx: commands.Context) -> None:
        """Devine quel anime est le plus populaire sur AniList."""
        await ctx.send("🎲 Préparation du mini‑jeu…")
        page = random.randint(1, 10)
        query = '''
        query ($page: Int) {
          Page(page: $page, perPage: 50) {
            media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
              title { romaji }
              popularity
              coverImage { medium }
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
            title="⬆️⬇️ Mini‑jeu : Quel anime est le plus populaire ?",
            description=(
                "Réponds `1` ou `2` selon ton intuition.\n"
                "1️⃣ {t1}\n"
                "2️⃣ {t2}"
            ).format(t1=choice1["title"]["romaji"], t2=choice2["title"]["romaji"]),
            color=discord.Color.orange(),
        )
        if choice1.get("coverImage") and choice2.get("coverImage"):
            embed.set_thumbnail(url=choice1["coverImage"]["medium"])
        await ctx.send(embed=embed)

        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel and m.content.strip() in {"1", "2"}

        try:
            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            answer = msg.content.strip()
            pop1 = choice1.get("popularity", 0)
            pop2 = choice2.get("popularity", 0)
            correct = "1" if pop1 >= pop2 else "2"
            if answer == correct:
                await ctx.send(f"✅ Bravo ! **{choice1['title']['romaji']}** a une popularité de {pop1} et **{choice2['title']['romaji']}** de {pop2}. Tu gagnes 5 XP !")
                core.add_xp(ctx.author.id, 5)
                core.add_mini_score(ctx.author.id, "higherlower", 1)
            else:
                await ctx.send(f"❌ Mauvais choix. **{choice1['title']['romaji']}** : {pop1}, **{choice2['title']['romaji']}** : {pop2}.")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé ! Jeu annulé.")

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
              coverImage { medium }
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
            img_url = anime.get("coverImage", {}).get("medium")
            if img_url:
                embed.set_thumbnail(url=img_url)
            await ctx.send(embed=embed)

            def check(m: discord.Message) -> bool:
                return m.author == ctx.author and m.channel == ctx.channel

            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            try:
                guessed_year = int(msg.content.strip())
                if abs(guessed_year - year) <= 1:
                    await ctx.send(f"✅ Bravo ! L'année était bien **{year}** (tu as répondu {guessed_year}). Tu gagnes 8 XP !")
                    core.add_xp(ctx.author.id, 8)
                    core.add_mini_score(ctx.author.id, "guessyear", 1)
                else:
                    await ctx.send(f"❌ Raté. L'année était **{year}** (tu as répondu {guessed_year}).")
            except ValueError:
                await ctx.send(f"❌ Format invalide. L'année était **{year}**.")
        except (Exception, asyncio.TimeoutError):
            await ctx.send("❌ Une erreur s'est produite ou temps écoulé.")

    @commands.command(name="highermean")
    async def higher_mean(self, ctx: commands.Context) -> None:
        """Compare les notes moyennes de deux animes."""
        await ctx.send("📊 Préparation du mini‑jeu…")
        page = random.randint(1, 10)
        query = '''
        query ($page: Int) {
          Page(perPage: 50, page: $page) {
            media(type: ANIME, isAdult: false, sort: SCORE_DESC) {
              title { romaji }
              meanScore
              coverImage { medium }
            }
          }
        }
        '''
        data = core.query_anilist(query, {"page": page})
        try:
            anime_list = data["data"]["Page"]["media"]
            if len(anime_list) < 2:
                await ctx.send("❌ Pas assez d'animes pour jouer.")
                return

            a1, a2 = random.sample(anime_list, 2)
            t1, s1 = a1["title"]["romaji"], a1.get("meanScore", 0)
            t2, s2 = a2["title"]["romaji"], a2.get("meanScore", 0)

            embed = discord.Embed(
                title="🎖️ Mini‑jeu : Quelle note est la plus haute ?",
                description=(
                    "Réponds `1` ou `2` selon toi.\n"
                    f"1️⃣ {t1}\n"
                    f"2️⃣ {t2}"
                ),
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)

            def check(m: discord.Message) -> bool:
                return m.author == ctx.author and m.channel == ctx.channel and m.content.strip() in {"1", "2"}

            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            answer = msg.content.strip()
            correct = "1" if s1 >= s2 else "2"
            if answer == correct:
                await ctx.send(f"✅ Bien joué ! **{t1}** : {s1}/100 – **{t2}** : {s2}/100. Tu gagnes 5 XP !")
                core.add_xp(ctx.author.id, 5)
                core.add_mini_score(ctx.author.id, "highermean", 1)
            else:
                await ctx.send(f"❌ Mauvais choix. **{t1}** : {s1}/100, **{t2}** : {s2}/100.")
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
                  coverImage { medium }
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
        img_url = anime.get("coverImage", {}).get("medium")
        if img_url:
            embed.set_thumbnail(url=img_url)
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
                    core.add_xp(ctx.author.id, 8)
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
                  coverImage { medium }
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
        img_url = anime.get("coverImage", {}).get("medium")
        if img_url:
            embed.set_thumbnail(url=img_url)
        await ctx.send(embed=embed)

        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for("message", timeout=20.0, check=check)
            guess = msg.content.strip().lower()
            if guess in [g.lower() for g in genres]:
                await ctx.send(f"✅ Exact ! Les genres de **{title}** incluent {', '.join(anime['genres'])}. Tu gagnes 5 XP !")
                core.add_xp(ctx.author.id, 5)
                core.add_mini_score(ctx.author.id, "guessgenre", 1)
            else:
                await ctx.send(f"❌ Mauvaise réponse. Les genres de **{title}** étaient : {', '.join(anime['genres'])}.")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé ! Le mini‑jeu est annulé.")

    @commands.command(name="guesscharacter")
    async def guess_character(self, ctx: commands.Context) -> None:
        """Devine le personnage d'anime affiché."""
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

        try:
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
                description="Quel est le nom de ce personnage ?",
                color=discord.Color.blurple()
            )
            embed.set_image(url=correct_image)
            for i, opt in enumerate(options, 1):
                embed.add_field(name=f"{i}️⃣", value=opt, inline=False)
            await ctx.send(embed=embed)

            def check(m: discord.Message) -> bool:
                return (m.author == ctx.author and
                        m.channel == ctx.channel and
                        m.content.isdigit() and
                        1 <= int(m.content) <= 4)

            msg = await self.bot.wait_for("message", timeout=20.0, check=check)
            choice = int(msg.content) - 1

            if choice == correct_index:
                await ctx.send("✅ Bien joué ! Tu gagnes 5 XP !")
                core.add_xp(ctx.author.id, 5)
                core.add_mini_score(ctx.author.id, "guesscharacter", 1)
            else:
                await ctx.send(f"❌ Mauvaise réponse ! C'était : **{correct_name}**")

        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé ! C'était : **{correct_name}**")
        except Exception as e:
            await ctx.send("❌ Une erreur s'est produite.")

    @commands.command(name="guessop")
    async def guess_op(self, ctx: commands.Context) -> None:
        """Devine l'opening d'un anime."""
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

            vc = await voice_channel.connect()
            audio_source = discord.FFmpegPCMAudio(
                os.path.join(audio_folder, selected_file),
                executable='ffmpeg'
            )
            vc.play(audio_source)

            embed = discord.Embed(
                title="🎵 Devine l'opening !",
                description="De quel anime vient cet opening ?",
                color=discord.Color.purple()
            )
            for i, title in enumerate(choices, 1):
                embed.add_field(name=f"{i}️⃣", value=title, inline=False)
            await ctx.send(embed=embed)

            def check(m: discord.Message) -> bool:
                return (m.author == ctx.author and
                        m.channel == ctx.channel and
                        m.content.isdigit() and
                        1 <= int(m.content) <= 4)

            try:
                msg = await self.bot.wait_for("message", timeout=30.0, check=check)
                choice = int(msg.content) - 1

                if choice == correct_index:
                    await ctx.send("✅ Bonne réponse ! Tu gagnes 5 XP !")
                    core.add_xp(ctx.author.id, 5)
                    core.add_mini_score(ctx.author.id, "guessop", 1)
                else:
                    await ctx.send(f"❌ Mauvaise réponse ! C'était : **{correct_anime}**")

            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{correct_anime}**")

        except Exception as e:
            await ctx.send("❌ Une erreur s'est produite.")

        finally:
            try:
                await vc.disconnect()
            except:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiniGames(bot))