"""
Mini‑games commands.

This cog regroupe plusieurs petits jeux pour divertir les utilisateurs :
* **Higher/Lower** : devinez quel anime est le plus populaire.
* **Guess Year** : devinez l’année de diffusion d’un anime.
* **Higher Mean** : devinez quelle série a la meilleure note moyenne.
* **Guess Episodes** : devinez le nombre d’épisodes d’une série.
* **Guess Genre** : trouvez un des genres principaux d’un anime.

Les jeux attribuent de l’XP et enregistrent un mini‑score afin de
récompenser les joueurs les plus actifs.
"""

from __future__ import annotations

import random
from typing import Optional

import discord
from discord.ext import commands

from restructured_bot.modules import core


class MiniGames(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="higherlower")
    async def higher_lower(self, ctx: commands.Context) -> None:
        """Devine quel anime est le plus populaire sur AniList.

        Le bot sélectionne deux animes au hasard parmi les plus populaires.
        Réponds `1` ou `2` pour indiquer lequel tu penses être le plus
        populaire. Une bonne réponse te rapporte 5 XP.
        """
        await ctx.send("🎲 Préparation du mini‑jeu…")
        # Fetch a batch of popular anime
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
        # Compose embed presenting the two options
        embed = discord.Embed(
            title="⬆️⬇️ Mini‑jeu : Quel anime est le plus populaire ?",
            description=(
                "Réponds `1` ou `2` selon ton intuition.\n"
                "1️⃣ {t1}\n"
                "2️⃣ {t2}"
            ).format(t1=choice1["title"]["romaji"], t2=choice2["title"]["romaji"]),
            color=discord.Color.orange(),
        )
        # Optionally display covers
        if choice1.get("coverImage") and choice2.get("coverImage"):
            embed.set_thumbnail(url=choice1["coverImage"]["medium"])
            # We cannot display two thumbnails; we rely on text descriptions
        await ctx.send(embed=embed)
        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel and m.content.strip() in {"1", "2"}
        try:
            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
        except Exception:
            await ctx.send("⏰ Temps écoulé ! Jeu annulé.")
            return
        answer = msg.content.strip()
        pop1 = choice1.get("popularity", 0)
        pop2 = choice2.get("popularity", 0)
        correct = "1" if pop1 >= pop2 else "2"
        if answer == correct:
            await ctx.send(f"✅ Bravo! **{choice1['title']['romaji']}** a une popularité de {pop1} et **{choice2['title']['romaji']}** de {pop2}. Tu gagnes 5 XP !")
            core.add_xp(ctx.author.id, 5)
            # Record mini-game score
            core.add_mini_score(ctx.author.id, "higherlower", 1)
        else:
            await ctx.send(f"❌ Mauvais choix. **{choice1['title']['romaji']}** : {pop1}, **{choice2['title']['romaji']}** : {pop2}.")

    @commands.command(name="guessyear")
    async def guess_year(self, ctx: commands.Context) -> None:
        """Devine l’année de diffusion d’un anime au hasard.

        Le bot choisit un anime populaire et te demande son année de sortie. Tu as
        15 secondes pour répondre. Une réponse exacte ou avec une marge de ±1 an
        rapporte 8 XP, sinon la bonne année est affichée.
        """
        await ctx.send("🗓️ Chargement d’un anime…")
        # Fetch a random anime
        page = random.randint(1, 500)
        query = f'''
        query {{
          Page(perPage: 1, page: {page}) {{
            media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {{
              title {{ romaji }}
              startDate {{ year }}
              coverImage {{ medium }}
            }}
          }}
        }}
        '''
        data = core.query_anilist(query)
        try:
            anime = data["data"]["Page"]["media"][0]
        except Exception:
            await ctx.send("❌ Impossible de récupérer un anime.")
            return
        title = anime["title"]["romaji"]
        year = anime.get("startDate", {}).get("year")
        if not year:
            await ctx.send("❌ L’année de cet anime est indisponible.")
            return
        embed = discord.Embed(
            title="📅 Mini‑jeu : Devine l’année !",
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
        try:
            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
        except Exception:
            await ctx.send("⏰ Temps écoulé ! Le mini‑jeu est annulé.")
            return
        try:
            guessed_year = int(msg.content.strip())
        except ValueError:
            await ctx.send(f"❌ Format invalide. L’année était **{year}**.")
            return
        # Determine if guess is correct within ±1
        if abs(guessed_year - year) <= 1:
            await ctx.send(f"✅ Bravo ! L’année était bien **{year}** (tu as répondu {guessed_year}). Tu gagnes 8 XP !")
            core.add_xp(ctx.author.id, 8)
            core.add_mini_score(ctx.author.id, "guessyear", 1)
        else:
            await ctx.send(f"❌ Raté. L’année était **{year}** (tu as répondu {guessed_year}).")

    @commands.command(name="highermean")
    async def higher_mean(self, ctx: commands.Context) -> None:
        """Compare les notes moyennes de deux animes.

        Deux animes sont sélectionnés et tu dois deviner lequel a la
        meilleure note moyenne sur AniList. Une bonne réponse rapporte 5 XP.
        """
        await ctx.send("📊 Préparation du mini‑jeu…")
        page = random.randint(1, 10)
        query = f'''
        query {{
          Page(perPage: 50, page: {page}) {{
            media(type: ANIME, isAdult: false, sort: SCORE_DESC) {{
              title {{ romaji }}
              meanScore
              coverImage {{ medium }}
            }}
          }}
        }}
        '''
        data = core.query_anilist(query)
        try:
            anime_list = data["data"]["Page"]["media"]
        except Exception:
            await ctx.send("❌ Impossible de récupérer des données.")
            return
        if len(anime_list) < 2:
            await ctx.send("❌ Pas assez d’animes pour jouer.")
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
        try:
            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
        except Exception:
            await ctx.send("⏰ Temps écoulé ! Jeu annulé.")
            return
        answer = msg.content.strip()
        correct = "1" if s1 >= s2 else "2"
        if answer == correct:
            await ctx.send(f"✅ Bien joué ! **{t1}** : {s1}/100 – **{t2}** : {s2}/100. Tu gagnes 5 XP !")
            core.add_xp(ctx.author.id, 5)
            core.add_mini_score(ctx.author.id, "highermean", 1)
        else:
            await ctx.send(f"❌ Mauvais choix. **{t1}** : {s1}/100, **{t2}** : {s2}/100.")

    @commands.command(name="guessepisodes")
    async def guess_episodes(self, ctx: commands.Context) -> None:
        """Devine le nombre d'épisodes d’un anime.

        Le bot choisit au hasard un anime non‑adulte dont le nombre
        d'épisodes est connu. Réponds par un entier ; une réponse
        exacte ou dans une marge de ±10 % (ou ±5 épisodes) rapporte 8 XP.
        """
        await ctx.send("🎬 Sélection d’un anime…")
        anime = None
        # On tente plusieurs fois de trouver un anime avec un nombre d'épisodes
        for _ in range(5):
            page = random.randint(1, 500)
            query = f'''
            query {{
              Page(perPage: 1, page: {page}) {{
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {{
                  title {{ romaji }}
                  episodes
                  coverImage {{ medium }}
                }}
              }}
            }}
            '''
            data = core.query_anilist(query)
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
            title="🎞️ Mini‑jeu : Combien d’épisodes ?",
            description=(
                f"Combien d’épisodes compte **{title}** ?\n"
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
        except Exception:
            await ctx.send("⏰ Temps écoulé ! Le mini‑jeu est annulé.")
            return
        # Analyse de la réponse
        try:
            guessed = int(msg.content.strip())
        except ValueError:
            await ctx.send(f"❌ Ce n’est pas un nombre valide. **{title}** a **{episodes}** épisodes.")
            return
        # Tolérance : ±10 % ou ±5 épisodes (le plus grand des deux)
        tolerance = max(int(episodes * 0.1), 5)
        if abs(guessed - episodes) <= tolerance:
            await ctx.send(
                f"✅ Bravo ! **{title}** compte {episodes} épisodes (tu as répondu {guessed}). Tu gagnes 8 XP !"
            )
            core.add_xp(ctx.author.id, 8)
            core.add_mini_score(ctx.author.id, "guessepisodes", 1)
        else:
            await ctx.send(f"❌ Raté. **{title}** compte {episodes} épisodes (tu as répondu {guessed}).")

    @commands.command(name="guessgenre")
    async def guess_genre(self, ctx: commands.Context) -> None:
        """Devine un des genres d’un anime.

        Le bot choisit un anime populaire et t’invite à deviner l’un de
        ses genres. Une réponse correcte rapporte 5 XP. Si plusieurs
        genres existent, n’importe lequel suffit.
        """
        await ctx.send("🎭 Sélection d’un anime…")
        # Cherche un anime avec des genres listés
        anime = None
        for _ in range(5):
            page = random.randint(1, 500)
            query = f'''
            query {{
              Page(perPage: 1, page: {page}) {{
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {{
                  title {{ romaji }}
                  genres
                  coverImage {{ medium }}
                }}
              }}
            }}
            '''
            data = core.query_anilist(query)
            try:
                candidate = data["data"]["Page"]["media"][0]
                genres = candidate.get("genres")
                if genres:
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
        except Exception:
            await ctx.send("⏰ Temps écoulé ! Le mini‑jeu est annulé.")
            return
        guess = msg.content.strip().lower()
        if guess in [g.lower() for g in genres]:
            await ctx.send(f"✅ Exact ! Les genres de **{title}** incluent {', '.join(anime['genres'])}. Tu gagnes 5 XP !")
            core.add_xp(ctx.author.id, 5)
            core.add_mini_score(ctx.author.id, "guessgenre", 1)
        else:
            await ctx.send(f"❌ Mauvaise réponse. Les genres de **{title}** étaient : {', '.join(anime['genres'])}.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiniGames(bot))
