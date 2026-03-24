"""
Mini-games commands.

* `/guess` — menu ou sous-commandes (year, episodes, genre, character) ; le menu lance le jeu
* `/higherlower` — popularité
* `/minijeux` — menu : sélection = lance le jeu (sauf duel → besoin d’un adversaire)
"""

from __future__ import annotations
import logging
import time
from collections import deque
import aiohttp
from PIL import Image
from io import BytesIO
import random
import asyncio
import discord
from discord.ext import commands
from discord.ui import View, Button, Select
from modules import core

LOG = logging.getLogger(__name__)

# --- Anti-spam /guess genre (réponses « faciles » trop souvent gagnantes) ---
_SPAM_GENRE_NAMES = frozenset({
    "action", "adventure", "comedy", "drama", "fantasy", "romance",
    "sci-fi", "sci fi", "slice of life", "mystery", "supernatural", "thriller",
    "horror", "psychological", "school", "sports", "music", "mecha",
    "ecchi", "shounen", "shoujo", "seinen", "josei",
})
_GUESS_GENRE_SPAM_STREAK: dict[int, int] = {}
_GUESS_GENRE_SPAM_TIMES: dict[int, deque[float]] = {}
_GUESS_GENRE_COOLDOWN_UNTIL: dict[int, float] = {}
_GUESS_GENRE_COOLDOWN_SEC = 120.0
_SPAM_WINDOW_SEC = 300.0
_SPAM_MAX_STREAK = 3  # au-delà : 4e victoire « facile » d’affilée → pénalité
_SPAM_MAX_IN_WINDOW = 3  # au-delà : 4e en 5 min → pénalité


def _guess_genre_is_spam_candidate(guess: str) -> bool:
    g = (guess or "").strip().lower()
    if g in _SPAM_GENRE_NAMES:
        return True
    g2 = g.replace("-", " ").strip()
    return g2 in _SPAM_GENRE_NAMES


def _guess_genre_prune_times(uid: int, now: float) -> deque[float]:
    dq = _GUESS_GENRE_SPAM_TIMES.setdefault(uid, deque(maxlen=32))
    while dq and now - dq[0] > _SPAM_WINDOW_SEC:
        dq.popleft()
    return dq


class HigherLowerView(View):
    def __init__(self, ctx, choice1, choice2):
        super().__init__(timeout=20)
        self.ctx = ctx
        self.choice1 = choice1
        self.choice2 = choice2
        self.result_sent = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ Ce mini-jeu n’est pas pour toi.", ephemeral=True)
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
            core.add_mini_score(interaction.user.id, "higherlower", 1)
        else:
            await interaction.response.send_message(
                f"❌ Mauvais choix. **{self.choice1['title']['romaji']}** : {pop1}, **{self.choice2['title']['romaji']}** : {pop2}."
            )
        self.stop()


class GuessHubSelect(Select):
    """Sous-menu /guess : lance directement le mode choisi."""

    def __init__(self) -> None:
        # Ne pas utiliser self._parent : réservé par discord.ui.Item (écrasé par super().__init__).
        super().__init__(
            custom_id="guess_hub_pick",
            placeholder="Choisis un mode Guess…",
            options=[
                discord.SelectOption(
                    label="📅 Année",
                    value="guess_year",
                    description="Devine l’année de diffusion",
                ),
                discord.SelectOption(
                    label="🎞️ Épisodes",
                    value="guess_episodes",
                    description="Devine le nombre d’épisodes",
                ),
                discord.SelectOption(
                    label="🎭 Genre",
                    value="guess_genre",
                    description="Trouve un des genres",
                ),
                discord.SelectOption(
                    label="👤 Personnage",
                    value="guess_character",
                    description="4 boutons — bon personnage",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        hub = self.view
        if not isinstance(hub, GuessHubView):
            LOG.error("GuessHubSelect: view inattendue %r", type(hub))
            return
        if interaction.user.id != hub.invoker_id:
            await interaction.response.send_message("❌ Ce menu n’est pas pour toi.", ephemeral=True)
            return
        key = self.values[0] if self.values else ""
        await hub.cog._run_minigame_choice(interaction, key)


class GuessHubView(View):
    def __init__(self, cog: "MiniGames", invoker_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.invoker_id = invoker_id
        self.add_item(GuessHubSelect())


class MinijeuxHubSelect(Select):
    def __init__(self) -> None:
        super().__init__(
            custom_id="minijeux_pick",
            placeholder="Choisis un mini-jeu…",
            options=[
                discord.SelectOption(
                    label="Higher / Lower",
                    value="higherlower",
                    description="Quel anime est le plus populaire ?",
                ),
                discord.SelectOption(
                    label="Guess — année",
                    value="guess_year",
                    description="Devine l’année de diffusion",
                ),
                discord.SelectOption(
                    label="Guess — épisodes",
                    value="guess_episodes",
                    description="Devine le nombre d’épisodes",
                ),
                discord.SelectOption(
                    label="Guess — genre",
                    value="guess_genre",
                    description="Devine un genre",
                ),
                discord.SelectOption(
                    label="Guess — personnage",
                    value="guess_character",
                    description="4 boutons, bon personnage",
                ),
                discord.SelectOption(
                    label="Guess OP (vocal)",
                    value="guessop",
                    description="Extraits audio — salon vocal requis",
                ),
                discord.SelectOption(
                    label="Anime quiz (solo)",
                    value="animequiz",
                    description="Quiz image / indices",
                ),
                discord.SelectOption(
                    label="Anime quiz multi",
                    value="animequizmulti",
                    description="Plusieurs questions d’affilée",
                ),
                discord.SelectOption(
                    label="Duel",
                    value="duel",
                    description="1v1 quiz contre un membre",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        hub = self.view
        if not isinstance(hub, MinijeuxHubView):
            LOG.error("MinijeuxHubSelect: view inattendue %r", type(hub))
            return
        if interaction.user.id != hub.invoker_id:
            await interaction.response.send_message("❌ Ce menu n’est pas pour toi.", ephemeral=True)
            return
        key = self.values[0] if self.values else ""
        await hub.cog._run_minigame_choice(interaction, key)


class MinijeuxHubView(View):
    """Menu : la sélection lance le jeu (sauf duel, qui nécessite un adversaire)."""

    def __init__(self, cog: "MiniGames", invoker_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.invoker_id = invoker_id
        self.add_item(MinijeuxHubSelect())


class MiniGames(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _run_minigame_choice(self, interaction: discord.Interaction, key: str) -> None:
        """Lance un mini-jeu depuis un menu (Select) : même logique que les commandes slash."""
        await interaction.response.defer(thinking=True)
        ctx = await self.bot.get_context(interaction)
        try:
            if key == "duel":
                await interaction.followup.send(
                    "⚔️ Un **duel** nécessite un adversaire : utilise **`/duel @membre`** "
                    "(manches + difficulté). Tu peux aussi taper **`!duel`**.",
                    ephemeral=True,
                )
                return
            if key == "higherlower":
                await self.higher_lower(ctx)
            elif key == "guess_year":
                await self.guess_year(ctx)
            elif key == "guess_episodes":
                await self.guess_episodes(ctx)
            elif key == "guess_genre":
                await self.guess_genre(ctx)
            elif key == "guess_character":
                await self.guess_character(ctx)
            elif key == "guessop":
                og = self.bot.get_cog("Openings")
                if og:
                    await og.guess_op(ctx)  # type: ignore[attr-defined]
                else:
                    await interaction.followup.send("❌ Guess OP indisponible.", ephemeral=True)
            elif key == "animequiz":
                qz = self.bot.get_cog("Quiz")
                if qz:
                    await qz.animequiz(ctx, "medium")  # type: ignore[attr-defined]
                else:
                    await interaction.followup.send("❌ Quiz indisponible.", ephemeral=True)
            elif key == "animequizmulti":
                qz = self.bot.get_cog("Quiz")
                if qz:
                    await qz.animequizmulti(ctx, 5)  # type: ignore[attr-defined]
                else:
                    await interaction.followup.send("❌ Quiz indisponible.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Option inconnue.", ephemeral=True)
        except Exception:
            LOG.exception("minigame dispatch failed (%s)", key)
            try:
                await interaction.followup.send(
                    "❌ Erreur en lançant le mini-jeu. Réessaie ou utilise la commande directement.",
                    ephemeral=True,
                )
            except Exception:
                pass

    # --------------------------------------
    # /guess (year, episodes, genre, character)
    # --------------------------------------
    @commands.hybrid_group(
        name="guess",
        invoke_without_command=True,
        description="Menu « devine » ou sous-commandes : year, episodes, genre, character.",
    )
    async def guess_cmd(self, ctx: commands.Context) -> None:
        if ctx.invoked_subcommand is not None:
            return
        em = discord.Embed(
            title="🎯 /guess — lance un mode",
            description=(
                "**Choisis ci-dessous** pour jouer tout de suite.\n\n"
                "Pour relancer sans menu la prochaine fois : "
                "**`/guess year`**, **`/guess episodes`**, **`/guess genre`**, **`/guess character`** "
                "(ou `!guess year`, etc.).\n"
                "Autres mini-jeux : **`/minijeux`**"
            ),
            color=discord.Color.purple(),
        )
        await ctx.send(embed=em, view=GuessHubView(self, ctx.author.id))

    @commands.hybrid_command(name="higherlower", description="Quel anime est le plus populaire ?")
    async def higher_lower(self, ctx: commands.Context):
        # Appelée en slash ? On évite le timeout 3s
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        await ctx.send("🎲 Préparation du mini-jeu…")

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
            await ctx.send(core.anilist_error_user_message())
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
                f"**1️⃣** {choice1['title']['romaji']}\n"
                f"**2️⃣** {choice2['title']['romaji']}"
            ),
            color=discord.Color.orange(),
        )

        url1 = choice1["coverImage"]["extraLarge"]
        url2 = choice2["coverImage"]["extraLarge"]

        async with aiohttp.ClientSession() as session:
            async with session.get(url1) as resp1:
                img1_bytes = await resp1.read()
            async with session.get(url2) as resp2:
                img2_bytes = await resp2.read()

        img1 = Image.open(BytesIO(img1_bytes)).convert("RGBA")
        img2 = Image.open(BytesIO(img2_bytes)).convert("RGBA")

        max_height = max(img1.height, img2.height)
        img1 = img1.resize((int(img1.width * max_height / img1.height), max_height))
        img2 = img2.resize((int(img2.width * max_height / img2.height), max_height))

        separator_width = 10
        total_width = img1.width + img2.width + separator_width
        combined = Image.new("RGBA", (total_width, max_height), (0, 0, 0, 255))
        combined.paste(img1, (0, 0))
        combined.paste(img2, (img1.width + separator_width, 0))

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

    # --------------------------------------
    # Guess Year
    # --------------------------------------
    @guess_cmd.command(
        name="year",
        aliases=["guessyear"],
        description="Devine l'année de diffusion d'un anime.",
    )
    async def guess_year(self, ctx: commands.Context) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

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
                title="📅 Mini-jeu : Devine l'année !",
                description=(
                    f"En quelle année **{title}** a-t-il commencé à être diffusé ?\n"
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

    # --------------------------------------
    # Guess Episodes
    # --------------------------------------
    @guess_cmd.command(
        name="episodes",
        aliases=["guessepisodes"],
        description="Devine le nombre d'épisodes d'un anime.",
    )
    async def guess_episodes(self, ctx: commands.Context) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

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
            await ctx.send(core.anilist_error_user_message())
            return

        title = anime["title"]["romaji"]
        episodes = anime["episodes"]
        embed = discord.Embed(
            title="🎞️ Mini-jeu : Combien d'épisodes ?",
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
            await ctx.send("⏰ Temps écoulé ! Le mini-jeu est annulé.")

    # --------------------------------------
    # Guess Genre
    # --------------------------------------
    @guess_cmd.command(
        name="genre",
        aliases=["guessgenre"],
        description="Devine un des genres d'un anime.",
    )
    async def guess_genre(self, ctx: commands.Context) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        uid = ctx.author.id
        now = time.monotonic()
        cd_until = _GUESS_GENRE_COOLDOWN_UNTIL.get(uid, 0.0)
        if now < cd_until:
            remaining = max(1, int(cd_until - now))
            await ctx.send(
                f"⏳ **Anti-spam genre** : attends encore **{remaining}s** avant de relancer `/guess genre`."
            )
            return

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
            await ctx.send(core.anilist_error_user_message())
            return

        title = anime["title"]["romaji"]
        genres = [g.lower() for g in anime.get("genres", [])]
        embed = discord.Embed(
            title="🎭 Mini-jeu : Devine le genre !",
            description=(
                f"Quel est un des genres de **{title}** ?\n"
                "Réponds par un genre (ex : `Action`, `Romance`).\n"
                "_Ne spamme pas uniquement les genres ultra courants : voir **anti-spam**._"
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
            guess_raw = msg.content.strip()
            guess = guess_raw.lower()
            if guess in [g.lower() for g in genres]:
                now2 = time.monotonic()
                spam = _guess_genre_is_spam_candidate(guess_raw)
                if spam:
                    dq = _guess_genre_prune_times(uid, now2)
                    dq.append(now2)
                    streak = _GUESS_GENRE_SPAM_STREAK.get(uid, 0) + 1
                    _GUESS_GENRE_SPAM_STREAK[uid] = streak
                    penalize = streak > _SPAM_MAX_STREAK or len(dq) > _SPAM_MAX_IN_WINDOW
                    if penalize:
                        _GUESS_GENRE_SPAM_STREAK.pop(uid, None)
                        _GUESS_GENRE_SPAM_TIMES.pop(uid, None)
                        _GUESS_GENRE_COOLDOWN_UNTIL[uid] = now2 + _GUESS_GENRE_COOLDOWN_SEC
                        await core.add_xp(self.bot, ctx.channel, ctx.author.id, -5, announce=False)
                        await ctx.send(
                            f"✅ Le genre **{guess_raw}** était bon, mais **anti-spam** : trop de réponses « faciles » "
                            f"(Action, Adventure, Comedy…) **plus de {_SPAM_MAX_STREAK} fois d’affilée** ou "
                            f"**plus de {_SPAM_MAX_IN_WINDOW} en 5 min**.\n"
                            f"**−5 XP** · cooldown **{int(_GUESS_GENRE_COOLDOWN_SEC)}s** sur `/guess genre`.\n"
                            f"Genres de **{title}** : {', '.join(anime['genres'])}."
                        )
                    else:
                        await ctx.send(
                            f"✅ Exact ! Les genres de **{title}** incluent {', '.join(anime['genres'])}. Tu gagnes 5 XP !"
                        )
                        await core.add_xp(self.bot, ctx.channel, ctx.author.id, 5)
                        core.add_mini_score(ctx.author.id, "guessgenre", 1)
                else:
                    _GUESS_GENRE_SPAM_STREAK.pop(uid, None)
                    _GUESS_GENRE_SPAM_TIMES.pop(uid, None)
                    await ctx.send(
                        f"✅ Exact ! Les genres de **{title}** incluent {', '.join(anime['genres'])}. Tu gagnes 5 XP !"
                    )
                    await core.add_xp(self.bot, ctx.channel, ctx.author.id, 5)
                    core.add_mini_score(ctx.author.id, "guessgenre", 1)
            else:
                _GUESS_GENRE_SPAM_STREAK.pop(uid, None)
                _GUESS_GENRE_SPAM_TIMES.pop(uid, None)
                await ctx.send(f"❌ Mauvaise réponse. Les genres de **{title}** étaient : {', '.join(anime['genres'])}.")
        except asyncio.TimeoutError:
            _GUESS_GENRE_SPAM_STREAK.pop(uid, None)
            _GUESS_GENRE_SPAM_TIMES.pop(uid, None)
            await ctx.send("⏰ Temps écoulé ! Le mini-jeu est annulé.")

    # --------------------------------------
    # Guess Character (boutons)
    # --------------------------------------
    @guess_cmd.command(
        name="character",
        aliases=["guesscharacter"],
        description="Devine le personnage d'anime (avec boutons).",
    )
    async def guess_character(self, ctx: commands.Context) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        page = random.randint(1, 100)
        query = '''
        query ($page: Int) {
          Page(page: $page, perPage: 4) {
            characters(sort: FAVOURITES_DESC) {
              name { full }
              image { large }
              media(type: ANIME) {
                nodes { title { romaji } }
              }
            }
          }
        }
        '''
        data = core.query_anilist(query, {"page": page})
        if not data or "data" not in data:
            await ctx.send(core.anilist_error_user_message())
            return

        characters = data["data"]["Page"]["characters"]
        if len(characters) < 4:
            await ctx.send("❌ Pas assez de personnages trouvés.")
            return

        correct = random.choice(characters)
        correct_name = correct["name"]["full"]
        correct_image = correct["image"]["large"]
        nodes = (correct.get("media", {}) or {}).get("nodes", [])
        correct_anime = (nodes[0]["title"]["romaji"] if nodes else "—")

        options = [c["name"]["full"] for c in characters]
        try:
            correct_index = options.index(correct_name)
        except ValueError:
            correct_index = random.randrange(len(options))

        embed = discord.Embed(
            title="👤 Devine le personnage !",
            description="Clique sur le bouton correspondant au bon nom.",
            color=discord.Color.blurple()
        )
        embed.set_image(url=correct_image)

        class GCView(View):
            def __init__(self, *, timeout: float = 20):
                super().__init__(timeout=timeout)
                self.resolved = False
                self.message: discord.Message | None = None

            async def on_timeout(self) -> None:
                if self.resolved or not self.message:
                    return
                self.resolved = True
                for item in self.children:
                    if isinstance(item, Button):
                        item.disabled = True
                await self.message.edit(
                    content=f"⏰ Temps écoulé. La bonne réponse était **{correct_name}** *(**{correct_anime}**)*.",
                    view=self
                )

        view = GCView(timeout=20)

        async def make_button_callback(inter: discord.Interaction, index: int):
            # Seul le lanceur peut cliquer
            if inter.user.id != ctx.author.id:
                await inter.response.send_message("❌ Ce n'est pas ton quiz !", ephemeral=True)
                return

            if view.resolved:
                try:
                    await inter.response.defer()
                except Exception:
                    pass
                return

            view.resolved = True
            for item in view.children:
                if isinstance(item, Button):
                    item.disabled = True

            if index == correct_index:
                txt = (f"✅ Bien joué **{inter.user.display_name}** ! "
                       f"C’était **{correct_name}** *(**{correct_anime}**)*. "
                       f"Tu gagnes **+5 XP**.")
                try:
                    await core.add_xp(self.bot, view.message.channel, inter.user.id, 5)
                except Exception:
                    pass
                try:
                    core.add_mini_score(inter.user.id, "guesscharacter", 1)
                except Exception:
                    pass
            else:
                txt = (f"❌ Mauvaise réponse. "
                       f"C’était **{correct_name}** *(**{correct_anime}**)*.")

            await inter.response.edit_message(content=txt, view=view)

        for i, opt in enumerate(options):
            btn = Button(label=opt, style=discord.ButtonStyle.primary)
            async def _cb(inter: discord.Interaction, idx=i):
                await make_button_callback(inter, idx)
            btn.callback = _cb
            view.add_item(btn)

        sent = await ctx.send(embed=embed, view=view)
        view.message = sent

    @commands.hybrid_command(
        name="minijeux",
        description="Menu des mini-jeux : choisis dans la liste pour lancer une partie.",
    )
    async def minijeux(self, ctx: commands.Context) -> None:
        em = discord.Embed(
            title="🎮 Mini-jeux",
            description=(
                "**Choisis un jeu** dans le menu — la partie **démarre tout de suite** dans ce salon "
                "(sauf **Duel** : il faut un adversaire → **`/duel @membre`**).\n\n"
                "Raccourcis : `/guess …`, `/higherlower`, `/guessop`, `/animequiz`, `/animequizmulti`."
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=em, view=MinijeuxHubView(self, ctx.author.id))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiniGames(bot))
