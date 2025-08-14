# cogs/opening.py
from __future__ import annotations
import os, random, asyncio
import discord
from discord.ext import commands

from modules import core
from modules.voice import play_clip_in_channel  # assure-toi que ce module existe

class GuessOPView(discord.ui.View):
    def __init__(self, bot: commands.Bot, ctx: commands.Context, voice_channel: discord.VoiceChannel,
                 choices: list[str], correct_index: int, timeout_sec: int = 30):
        super().__init__(timeout=timeout_sec)
        self.bot = bot
        self.ctx = ctx
        self.voice_channel = voice_channel
        self.choices = choices
        self.correct_index = correct_index
        self.already_answered: set[int] = set()
        self.winners_order: list[discord.Member] = []
        self.others_correct: list[discord.Member] = []
        self._lock = asyncio.Lock()
        self.message: discord.Message | None = None

        for i in range(4):
            self.add_item(GuessOPButton(index=i))

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

class GuessOPButton(discord.ui.Button):
    def __init__(self, index: int):
        super().__init__(label=str(index+1), style=discord.ButtonStyle.primary)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: GuessOPView = self.view  # type: ignore
        if interaction.user.bot:
            return await interaction.response.defer(ephemeral=True)

        # Doit être dans le même salon vocal
        if not interaction.user.voice or interaction.user.voice.channel != view.voice_channel:
            return await interaction.response.send_message(
                "🔇 Tu dois être dans **le même salon vocal** pour répondre.",
                ephemeral=True
            )

        async with view._lock:
            if interaction.user.id in view.already_answered:
                return await interaction.response.send_message("✋ Une seule réponse par joueur.", ephemeral=True)
            view.already_answered.add(interaction.user.id)

            if self.index == view.correct_index:
                if len(view.winners_order) < 3:
                    view.winners_order.append(interaction.user)
                    await interaction.response.send_message("✅ Bonne réponse !", ephemeral=True)
                    try:
                        await view.ctx.send(f"✅ {interaction.user.mention} a trouvé !")
                    except Exception:
                        pass
                else:
                    view.others_correct.append(interaction.user)
                    await interaction.response.send_message("✅ Bonne réponse (hors podium) !", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Mauvaise réponse.", ephemeral=True)

class Openings(commands.Cog):
    """Mini-jeu GuessOP (openings d’anime, boutons, multi-joueurs)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="guessop")
    async def guess_op(self, ctx: commands.Context) -> None:
        """Devine l'opening d'un anime (20s d'extrait, 4 boutons, podium de rapidité)."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("🔇 Tu dois être dans un **salon vocal** pour jouer.")
        voice_channel = ctx.author.voice.channel

        audio_folder = "assets/audio/openings"
        if not os.path.exists(audio_folder):
            return await ctx.send("❌ Le dossier des openings n'est pas configuré (`assets/audio/openings`).")
        files = [f for f in os.listdir(audio_folder) if f.endswith(".mp3")]
        if not files:
            return await ctx.send("❌ Aucun opening trouvé dans le dossier.")

        # Sélection d’un fichier audio
        selected_file = random.choice(files)
        filepath = os.path.join(audio_folder, selected_file)
        correct_anime = os.path.splitext(selected_file)[0]

        # 4 choix : correct + 3 leurres AniList
        query = '''
        query {
          Page(perPage: 30) {
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
        while len(choices) < 4:
            choices.append(f"Option {len(choices)+1}")
        random.shuffle(choices)
        correct_index = choices.index(correct_anime)

        # Lance l’audio (20s) en tâche asynchrone
        asyncio.create_task(
            play_clip_in_channel(voice_channel, filepath, duration_sec=20, disconnect_after=True)
        )

        # Embed question
        em = discord.Embed(
            title="🎵 Devine l’opening !",
            description="Clique sur **1–4** pour répondre (30s).",
            color=discord.Color.purple()
        )
        for i, title in enumerate(choices, 1):
            em.add_field(name=f"{i}️⃣", value=title, inline=False)

        # Vue + boutons
        view = GuessOPView(self.bot, ctx, voice_channel, choices, correct_index, timeout_sec=30)
        msg = await ctx.send(embed=em, view=view)
        view.message = msg

        # Attendre fin
        try:
            await view.wait()
        except Exception:
            pass

        # Résultats + XP
        if not view.winners_order and not view.others_correct:
            return await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{correct_anime}**")

        podium_xp = [15, 10, 7]
        others_xp = 3
        award_lines = []

        for rank, user in enumerate(view.winners_order, start=1):
            xp = podium_xp[rank-1]
            award_lines.append(f"**#{rank}** {user.mention} — +{xp} XP")
            try:
                await core.add_xp(self.bot, ctx.channel, user.id, xp)
            except Exception:
                pass
            try:
                core.add_mini_score(user.id, "guessop", 1)
            except Exception:
                pass

        for user in view.others_correct:
            award_lines.append(f"• {user.mention} — +{others_xp} XP")
            try:
                await core.add_xp(self.bot, ctx.channel, user.id, others_xp)
            except Exception:
                pass
            try:
                core.add_mini_score(user.id, "guessop", 1)
            except Exception:
                pass

        res = discord.Embed(
            title="🏁 Résultats — Guess OP",
            description=f"✅ **Réponse :** {correct_anime}",
            color=discord.Color.gold()
        )
        if award_lines:
            res.add_field(name="Récompenses", value="\n".join(award_lines), inline=False)

        # Grise les boutons
        try:
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await msg.edit(view=view)
        except Exception:
            pass

        await ctx.send(embed=res)

async def setup(bot: commands.Bot):
    await bot.add_cog(Openings(bot))
