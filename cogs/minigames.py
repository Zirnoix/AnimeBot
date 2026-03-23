"""
Mini-games commands.

* `/guess` — groupe (year, episodes, genre, character)
* `/higherlower` — popularité
* `/minijeux` — menu avec rappel des commandes
"""

from __future__ import annotations
import aiohttp
from PIL import Image
from io import BytesIO
import random
import asyncio
import discord
from discord.ext import commands
from discord.ui import View, Button, Select
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


_MINIJEUX_LINES = {
    "higherlower": (
        "**Higher / Lower** — Tu vois 2 animes ; choisis le plus populaire (boutons).\n"
        "→ `/higherlower` · `!higherlower`"
    ),
    "guess_year": (
        "**Guess année** — Image + devine l’année de diffusion.\n"
        "→ `/guess year` · `!guess year`"
    ),
    "guess_episodes": (
        "**Guess épisodes** — Devine combien d’épisodes.\n"
        "→ `/guess episodes` · `!guess episodes`"
    ),
    "guess_genre": (
        "**Guess genre** — Trouve un des genres de l’anime.\n"
        "→ `/guess genre` · `!guess genre`"
    ),
    "guess_character": (
        "**Guess personnage** — 4 noms en boutons.\n"
        "→ `/guess character` · `!guess character`"
    ),
    "guessop": (
        "**Guess OP** — Écoute un opening (salon vocal obligatoire).\n"
        "→ `/guessop` · `!guessop`"
    ),
    "animequiz": (
        "**Anime quiz** — Questions solo avec image.\n"
        "→ `/animequiz` · `!animequiz`"
    ),
    "animequizmulti": (
        "**Anime quiz multi** — Enchaînement de questions.\n"
        "→ `/animequizmulti` · `!animequizmulti`"
    ),
    "duel": (
        "**Duel** — Défie quelqu’un en quiz.\n"
        "→ `/duel` · `!duel`"
    ),
}


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
        sel = self.values[0] if self.values else ""
        text = _MINIJEUX_LINES.get(sel, "Commande inconnue.")
        await interaction.response.send_message(text, ephemeral=True)


class MinijeuxHubView(View):
    """Menu : rappelle la commande slash (et préfixe) à lancer."""

    def __init__(self) -> None:
        super().__init__(timeout=180)
        self.add_item(MinijeuxHubSelect())


class MiniGames(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # --------------------------------------
    # /guess (year, episodes, genre, character)
    # --------------------------------------
    @commands.hybrid_group(
        name="guess",
        invoke_without_command=True,
        description="Mini-jeux « devine » : année, épisodes, genre, personnage.",
    )
    async def guess_cmd(self, ctx: commands.Context) -> None:
        if ctx.invoked_subcommand is not None:
            return
        em = discord.Embed(
            title="🎯 /guess — choisis une variante",
            description=(
                "• **`/guess year`** — année de première diffusion\n"
                "• **`/guess episodes`** — nombre d’épisodes\n"
                "• **`/guess genre`** — un des genres de l’anime\n"
                "• **`/guess character`** — personnage (4 boutons)\n\n"
                "En préfixe : `!guess year`, `!guess episodes`, etc.\n"
                "Pour tout voir : **`/minijeux`**"
            ),
            color=discord.Color.purple(),
        )
        await ctx.send(embed=em, ephemeral=bool(ctx.interaction))

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
        description="Menu des mini-jeux : choisis dans la liste pour voir la commande à lancer.",
    )
    async def minijeux(self, ctx: commands.Context) -> None:
        em = discord.Embed(
            title="🎮 Mini-jeux",
            description=(
                "Utilise le menu ci-dessous pour lire **ce que fait chaque jeu** et **quelle commande lancer** "
                "(le bot ne peut pas lancer un slash à ta place).\n\n"
                "• **Guess** — `/guess` puis `year`, `episodes`, `genre` ou `character`\n"
                "• **Higher / Lower** — `/higherlower`\n"
                "• **Guess OP** — `/guessop` (vocal)\n"
                "• **Quiz** — `/animequiz`, `/animequizmulti`\n"
                "• **Duel** — `/duel`"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=em, view=MinijeuxHubView())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiniGames(bot))
