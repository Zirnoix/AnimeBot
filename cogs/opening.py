# cogs/opening.py
from __future__ import annotations
import os, random, asyncio, re
from typing import List

import discord
from discord.ext import commands

from modules import core
from modules import voice              # <-- utilise ton helper voice.play_clip_in_channel
from modules import animethemes        # <-- provider AnimeThemes + filtres

# ==== Configuration ====
USE_ANIMETHEMES = True         # essaie AnimeThemes d'abord, sinon fallback local
DURATION_SEC = 20              # durée de l'extrait
ANSWER_TIMEOUT = 30            # temps pour répondre (secondes)

# Filtres AniList (appliqués quand on pioche via AnimeThemes)
MIN_YEAR = 2005
MIN_SCORE_10 = 5.0
BANNED_GENRES = {"mahou shoujo", "kids"}    # complète si besoin
BANNED_FORMATS = {"MUSIC"}                  # ajoute "ONA" si tu veux

LOCAL_AUDIO_FOLDER = "assets/audio/openings"   # fallback local

def _clean_title_from_filename(name: str) -> str:
    """Nettoie un nom de fichier en titre : retire extension, 'OP/ED', crochets, underscores…"""
    base = os.path.splitext(name)[0]
    base = re.sub(r"[\[\(].*?[\]\)]", "", base, flags=re.IGNORECASE)         # [..] ou (..)
    base = re.sub(r"\b(OP|OPENING|ED|ENDING)\s*\d*\b", "", base, flags=re.IGNORECASE)
    base = re.sub(r"[_\-]+", " ", base)
    base = re.sub(r"\s{2,}", " ", base).strip()
    return base or os.path.splitext(name)[0]


# ================== UI (boutons) ==================
class GuessOPView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        voice_channel: discord.VoiceChannel,
        choices: List[str],
        correct_index: int,
        timeout_sec: int = ANSWER_TIMEOUT
    ):
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
        # Grise les boutons à la fin
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
        super().__init__(label=str(index + 1), style=discord.ButtonStyle.primary)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: GuessOPView = self.view  # type: ignore
        if interaction.user.bot:
            return await interaction.response.defer(ephemeral=True)

        # doit être dans le même salon vocal que l’hôte du jeu
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


# ================== COG ==================
class Openings(commands.Cog):
    """Mini-jeu GuessOP (openings d’anime, boutons, multi-joueurs, audio 20s)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="guessop")
    async def guess_op(self, ctx: commands.Context) -> None:
        """Devine l'opening d'un anime (20s d'extrait, 4 boutons, podium de rapidité)."""
        # Vérif vocal
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("🔇 Tu dois être dans un **salon vocal** pour jouer.")
        voice_channel: discord.VoiceChannel = ctx.author.voice.channel

        correct_anime: str | None = None
        media_source: str | None = None     # URL (AnimeThemes) OU chemin local
        source_footer = ""

        # --------- 1) Essai AnimeThemes + filtres AniList ---------
        if USE_ANIMETHEMES:
            try:
                got = await animethemes.random_opening_filtered(
                    min_year=MIN_YEAR,
                    min_score_10=MIN_SCORE_10,
                    banned_genres=BANNED_GENRES,
                    banned_formats=BANNED_FORMATS,
                    max_attempts=12,
                )
            except Exception:
                got = None

            if got:
                title, theme_label, video_url = got
                correct_anime = title
                media_source = video_url
                source_footer = "Source OP : AnimeThemes.moe"
            else:
                # fallback local si aucun OP filtré trouvé
                pass

        # --------- 2) Fallback local ---------
        if not media_source:
            if not os.path.exists(LOCAL_AUDIO_FOLDER):
                return await ctx.send(
                    "❌ Aucun OP filtré trouvé et le dossier local n’existe pas "
                    f"(`{LOCAL_AUDIO_FOLDER}`)."
                )
            files = [f for f in os.listdir(LOCAL_AUDIO_FOLDER) if f.lower().endswith(".mp3")]
            if not files:
                return await ctx.send("❌ Aucun opening trouvé dans le dossier local.")
            pick = random.choice(files)
            media_source = os.path.join(LOCAL_AUDIO_FOLDER, pick)
            correct_anime = _clean_title_from_filename(pick)
            source_footer = "Source : fichiers locaux"

        # --------- 3) Prépare les 4 choix (leurres via AniList) ---------
        query = '''
        query {
          Page(perPage: 60) {
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
        tries = 0
        while len(choices) < 4 and pool and tries < 200:
            alt = _clean_title_from_filename(random.choice(pool))
            tries += 1
            if alt and alt.lower() != correct_anime.lower() and alt not in choices:
                choices.append(alt)
        while len(choices) < 4:
            choices.append(f"Option {len(choices) + 1}")
        random.shuffle(choices)
        correct_index = choices.index(correct_anime)

        # --------- 4) Lecture audio dans le vocal ---------
        try:
            await voice.play_clip_in_channel(
                voice_channel,
                filepath=media_source,     # URL (AnimeThemes) ou chemin local
                duration_sec=DURATION_SEC,
                disconnect_after=True
            )
        except Exception:
            # On n’annule pas la partie si l’audio foire (ffmpeg, réseau, permissions)
            await ctx.send("⚠️ Impossible de jouer l'extrait audio (ffmpeg / URL / permissions ?).")

        # --------- 5) Envoi de la question + boutons ---------
        em = discord.Embed(
            title="🎵 Devine l’opening !",
            description=f"Clique sur **1–4** pour répondre (**{ANSWER_TIMEOUT}s**).",
            color=discord.Color.purple()
        )
        for i, title in enumerate(choices, 1):
            em.add_field(name=f"{i}️⃣", value=title, inline=False)
        if source_footer:
            em.set_footer(text=source_footer)

        view = GuessOPView(self.bot, ctx, voice_channel, choices, correct_index, timeout_sec=ANSWER_TIMEOUT)
        msg = await ctx.send(embed=em, view=view)
        view.message = msg

        # --------- 6) Fin de manche & récompenses ---------
        try:
            await view.wait()
        except Exception:
            pass

        if not view.winners_order and not view.others_correct:
            # Désactive les boutons
            try:
                for item in view.children:
                    if isinstance(item, discord.ui.Button):
                        item.disabled = True
                await msg.edit(view=view)
            except Exception:
                pass
            return await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{correct_anime}**")

        podium_xp = [15, 10, 7]
        others_xp = 3
        award_lines = []

        # Podium
        for rank, user in enumerate(view.winners_order, start=1):
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

        # Autres bonnes réponses (hors top 3)
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
