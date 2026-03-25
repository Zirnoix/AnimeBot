"""
Mini-jeux communautaires : raid boss (planning hebdo + alerte admin), chain quiz,
« qui est-ce » (image floutée).

Commandes en slash (hybrid désactivé pour le préfixe sur les groupes admin — utiliser /).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
from datetime import datetime, time, timedelta
from typing import Any, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
from PIL import Image, ImageFilter

from modules import core
from modules.core import normalize

LOG = logging.getLogger(__name__)

SLASH_ONLY_MSG = "Cette commande est réservée au **slash** : utilise `/{}` dans la barre de commandes."


async def _require_slash(ctx: commands.Context, name: str) -> bool:
    """True si on peut continuer (invocation slash)."""
    if ctx.interaction is None:
        await ctx.send(SLASH_ONLY_MSG.format(name))
        return False
    return True


RAID_DATA_PATH = os.path.join("data", "boss_raid.json")
SORT_CHAIN = ("easy", "medium", "hard")
SORT_TO_ANILIST = {
    "easy": "POPULARITY_DESC",
    "medium": "SCORE_DESC",
    "hard": "TRENDING_DESC",
}

# guesswho : division taille, flou gaussien, timeout (s), XP si victoire
GUESSWHO_MODES: dict[str, tuple[int, float, float, int]] = {
    "easy": (5, 4.0, 55.0, 18),
    "medium": (8, 6.0, 45.0, 28),
    "hard": (12, 9.0, 38.0, 42),
}

_active_raids: dict[int, bool] = {}  # guild_id -> running


def _load_raid_cfg() -> dict[str, Any]:
    try:
        with open(RAID_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_raid_cfg(data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(RAID_DATA_PATH) or ".", exist_ok=True)
    with open(RAID_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _raid_target_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Salon configuré pour le raid (`/raidconfig canal`), sinon None."""
    cfg = _load_raid_cfg().get(str(guild.id), {})
    cid = cfg.get("channel_id")
    if not cid:
        return None
    ch = guild.get_channel(int(cid))
    if isinstance(ch, discord.TextChannel):
        return ch
    return None


def _next_raid_moment(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    """Prochaine occurrence weekday (0=lun) + heure:minute après `now`."""
    tz = now.tzinfo or core.TIMEZONE
    wd = int(weekday) % 7
    for delta in range(14):
        day = (now + timedelta(days=delta)).date()
        if day.weekday() != wd:
            continue
        cand = datetime.combine(day, time(hour, minute), tzinfo=tz)
        if cand > now:
            return cand
    return now + timedelta(days=7)


# ---------- Boss raid : combat ----------


class BossRaidRoundView(View):
    def __init__(
        self,
        *,
        cog: CommunityGames,
        channel: discord.TextChannel,
        correct_index: int,
        options: list[str],
        correct_name: str,
        anime_hint: str,
        damage: int,
        round_n: int,
        max_rounds: int,
        hp_left: list[int],  # mutable [hp]
        guild_id: int,
    ):
        super().__init__(timeout=45.0)
        self.cog = cog
        self.channel = channel
        self.correct_index = correct_index
        self.options = options
        self.correct_name = correct_name
        self.anime_hint = anime_hint
        self.damage = damage
        self.round_n = round_n
        self.max_rounds = max_rounds
        self.hp_left = hp_left
        self.guild_id = guild_id
        self.resolved = False
        self.message: discord.Message | None = None

        for i, label in enumerate(options):
            b = Button(label=label[:79], style=discord.ButtonStyle.primary, row=i // 2)
            b.callback = self._make_cb(i)
            self.add_item(b)

    def _make_cb(self, idx: int):
        async def _cb(interaction: discord.Interaction) -> None:
            await self._handle(interaction, idx)

        return _cb

    async def _handle(self, interaction: discord.Interaction, idx: int) -> None:
        if self.resolved:
            try:
                await interaction.response.defer()
            except Exception:
                pass
            return
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("❌ Partie sur un autre serveur.", ephemeral=True)
            return

        self.resolved = True
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True

        uid = interaction.user.id
        if idx == self.correct_index:
            self.hp_left[0] = max(0, self.hp_left[0] - self.damage)
            core.add_mini_score(uid, "bossraid", 1)
            try:
                await core.add_xp(self.cog.bot, self.channel, uid, 8, announce=False)
            except Exception:
                pass
            msg = (
                f"✅ **{interaction.user.display_name}** inflige **{self.damage}** dégâts ! "
                f"*(**{self.correct_name}** — {self.anime_hint})*\n"
                f"❤️ Boss : **{self.hp_left[0]}** HP · Manche **{self.round_n}/{self.max_rounds}**"
            )
        else:
            msg = (
                f"❌ **{interaction.user.display_name}** rate ! C’était **{self.correct_name}** "
                f"({self.anime_hint}).\n"
                f"❤️ Boss : **{self.hp_left[0]}** HP"
            )

        await interaction.response.edit_message(content=msg, embed=None, view=self)

        await asyncio.sleep(2.0)
        if self.hp_left[0] <= 0:
            await self.channel.send(
                f"🏆 **Raid terminé !** Le boss est vaincu ! GG à tous — **{interaction.user.display_name}** "
                f"a porté le coup final de la manche."
            )
            _active_raids.pop(self.guild_id, None)
            return
        if self.round_n >= self.max_rounds:
            await self.channel.send(
                f"⏱️ **Fin du raid** — le boss a encore **{self.hp_left[0]}** HP. Réessayez la semaine prochaine !"
            )
            _active_raids.pop(self.guild_id, None)
            return
        await self.cog._raid_next_round(self.channel, self.guild_id, self.hp_left[0], self.round_n + 1)

    async def on_timeout(self) -> None:
        if self.resolved:
            return
        self.resolved = True
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    content=f"⏰ Temps écoulé — c’était **{self.correct_name}**. Le boss garde ses HP (**{self.hp_left[0]}**).",
                    embed=None,
                    view=self,
                )
            except Exception:
                pass
        await asyncio.sleep(2.0)
        if self.hp_left[0] > 0 and self.round_n < self.max_rounds:
            await self.cog._raid_next_round(self.channel, self.guild_id, self.hp_left[0], self.round_n + 1)
        else:
            _active_raids.pop(self.guild_id, None)


class CommunityGames(commands.Cog):
    """Raid boss, chain quiz, guesswho."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.raid_scheduler.start()

    async def cog_unload(self) -> None:
        self.raid_scheduler.cancel()

    # ---------- Raid : logique ----------

    async def _raid_next_round(
        self,
        channel: discord.TextChannel,
        guild_id: int,
        hp: int,
        round_n: int,
        max_rounds: int = 8,
    ) -> None:
        page = random.randint(1, 80)
        query = """
        query ($page: Int) {
          Page(page: $page, perPage: 4) {
            characters(sort: FAVOURITES_DESC) {
              name { full }
              image { large }
              media(type: ANIME) { nodes { title { romaji } } }
            }
          }
        }
        """
        data = core.query_anilist(query, {"page": page})
        if not data or "data" not in data:
            await channel.send(core.anilist_error_user_message())
            _active_raids.pop(guild_id, None)
            return
        chars = data["data"]["Page"]["characters"]
        if len(chars) < 4:
            await channel.send("❌ Pas assez de données personnages.")
            _active_raids.pop(guild_id, None)
            return
        correct = random.choice(chars)
        correct_name = correct["name"]["full"]
        img = (correct.get("image") or {}).get("large")
        nodes = (correct.get("media") or {}).get("nodes") or []
        anime_hint = (nodes[0]["title"]["romaji"] if nodes else "—")
        options = [c["name"]["full"] for c in chars]
        random.shuffle(options)
        try:
            correct_index = options.index(correct_name)
        except ValueError:
            correct_index = 0

        hp_box = [hp]
        damage = random.randint(700, 1100)

        emb = discord.Embed(
            title=f"👹 Boss Raid — Manche {round_n}/{max_rounds}",
            description=(
                f"❤️ **{hp}** HP · Premier à cliquer sur le **bon** personnage inflige des dégâts au boss.\n"
                f"*(Anime lié : {anime_hint})*"
            ),
            color=discord.Color.dark_red(),
        )
        if img:
            emb.set_image(url=img)

        view = BossRaidRoundView(
            cog=self,
            channel=channel,
            correct_index=correct_index,
            options=options,
            correct_name=correct_name,
            anime_hint=anime_hint,
            damage=damage,
            round_n=round_n,
            max_rounds=max_rounds,
            hp_left=hp_box,
            guild_id=guild_id,
        )
        msg = await channel.send(embed=emb, view=view)
        view.message = msg

    async def _start_boss_raid(self, guild: discord.Guild, channel: discord.TextChannel, week_key: str) -> None:
        if _active_raids.get(guild.id):
            return
        _active_raids[guild.id] = True
        cfg = _load_raid_cfg()
        gk = str(guild.id)
        if gk in cfg:
            cfg[gk]["raid_started_for_week"] = week_key
            _save_raid_cfg(cfg)

        await channel.send(
            "⚔️ **BOSS RAID** — La bataille commence ! Cliquez vite sur le bon personnage à chaque manche.\n"
            "_Toute l’équipe participe : le premier bon clic compte._"
        )
        await self._raid_next_round(channel, guild.id, hp=10000, round_n=1)

    @tasks.loop(minutes=1.0)
    async def raid_scheduler(self) -> None:
        cfg = _load_raid_cfg()
        now = datetime.now(core.TIMEZONE)
        for gid_str, c in list(cfg.items()):
            if not c.get("enabled"):
                continue
            try:
                gid = int(gid_str)
            except ValueError:
                continue
            ch_id = c.get("channel_id")
            if not ch_id:
                continue
            channel = self.bot.get_channel(int(ch_id))
            if not isinstance(channel, discord.TextChannel):
                continue
            guild = channel.guild
            weekday = int(c.get("weekday", 5))
            hour = int(c.get("hour", 20))
            minute = int(c.get("minute", 0))
            raid_at = _next_raid_moment(now, weekday, hour, minute)
            wkey = _week_key(raid_at)
            alert_at = raid_at - timedelta(hours=1)

            if c.get("alert_sent_for_week") != wkey and alert_at <= now < raid_at:
                try:
                    await channel.send(
                        "@here ⏰ **Boss Raid** dans **1 h** — préparez-vous (quiz / persos AniList) !"
                    )
                except Exception as e:
                    LOG.warning("raid alert: %s", e)
                c["alert_sent_for_week"] = wkey
                _save_raid_cfg(cfg)

            if (
                c.get("raid_started_for_week") != wkey
                and raid_at <= now < raid_at + timedelta(minutes=4)
                and not _active_raids.get(guild.id)
            ):
                try:
                    await self._start_boss_raid(guild, channel, wkey)
                except Exception as e:
                    LOG.exception("raid auto-start: %s", e)

    @raid_scheduler.before_loop
    async def _raid_sched_before(self) -> None:
        await self.bot.wait_until_ready()

    raidconfig = app_commands.Group(
        name="raidconfig",
        description="Configurer le raid boss hebdomadaire (administrateurs uniquement).",
    )

    @raidconfig.command(name="canal", description="Définir le salon des annonces et du combat de raid.")
    @app_commands.describe(channel="Salon texte (défaut : salon actuel)")
    @app_commands.default_permissions(administrator=True)
    async def raid_canal(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("❌ Salon texte requis.", ephemeral=True)
            return
        cfg = _load_raid_cfg()
        cfg[str(interaction.guild.id)] = cfg.get(str(interaction.guild.id), {})
        cfg[str(interaction.guild.id)]["channel_id"] = ch.id
        _save_raid_cfg(cfg)
        await interaction.response.send_message(f"✅ Salon de raid : {ch.mention}", ephemeral=True)

    @raidconfig.command(name="horaire", description="Jour et heure du raid (fuseau du bot : BOT_TIMEZONE).")
    @app_commands.describe(
        weekday="0 = lundi … 6 = dimanche",
        hour="0–23",
        minute="0–59",
    )
    @app_commands.default_permissions(administrator=True)
    async def raid_horaire(
        self,
        interaction: discord.Interaction,
        weekday: app_commands.Range[int, 0, 6],
        hour: app_commands.Range[int, 0, 23],
        minute: app_commands.Range[int, 0, 59],
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        cfg = _load_raid_cfg()
        cfg[str(interaction.guild.id)] = cfg.get(str(interaction.guild.id), {})
        cfg[str(interaction.guild.id)]["weekday"] = int(weekday)
        cfg[str(interaction.guild.id)]["hour"] = int(hour)
        cfg[str(interaction.guild.id)]["minute"] = int(minute)
        _save_raid_cfg(cfg)
        await interaction.response.send_message(
            f"✅ Raid planifié : **jour {weekday}** à **{hour:02d}:{minute:02d}** (voir `BOT_TIMEZONE`).",
            ephemeral=True,
        )

    @raidconfig.command(name="activer", description="Activer ou désactiver le raid automatique.")
    @app_commands.default_permissions(administrator=True)
    async def raid_activer(self, interaction: discord.Interaction, actif: bool) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        cfg = _load_raid_cfg()
        cfg[str(interaction.guild.id)] = cfg.get(str(interaction.guild.id), {})
        cfg[str(interaction.guild.id)]["enabled"] = actif
        _save_raid_cfg(cfg)
        await interaction.response.send_message(f"✅ Raid auto : **{'activé' if actif else 'désactivé'}**.", ephemeral=True)

    @raidconfig.command(name="statut", description="Afficher la config actuelle du raid.")
    @app_commands.default_permissions(administrator=True)
    async def raid_statut(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        cfg = _load_raid_cfg().get(str(interaction.guild.id), {})
        ch = cfg.get("channel_id")
        ch_txt = f"<#{ch}>" if ch else "—"
        now = datetime.now(core.TIMEZONE)
        wd = int(cfg.get("weekday", 5))
        h = int(cfg.get("hour", 20))
        m = int(cfg.get("minute", 0))
        nxt = _next_raid_moment(now, wd, h, m)
        await interaction.response.send_message(
            f"**Raid boss**\n"
            f"• Salon : {ch_txt}\n"
            f"• Horaire : jour **{wd}** à **{h:02d}:{m:02d}**\n"
            f"• Actif : **{cfg.get('enabled', False)}**\n"
            f"• Prochain créneau (calcul) : <t:{int(nxt.timestamp())}:F>\n"
            f"_Alerte ~1 h avant dans le salon._",
            ephemeral=True,
        )

    @app_commands.command(name="raidstart", description="Lancer un raid boss maintenant (admin).")
    @app_commands.default_permissions(administrator=True)
    async def raid_start(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if _active_raids.get(interaction.guild.id):
            await interaction.followup.send("Un raid est déjà en cours sur ce serveur.", ephemeral=True)
            return
        target = _raid_target_channel(interaction.guild)
        if target is None:
            await interaction.followup.send(
                "❌ Aucun salon de raid configuré. Utilise d’abord **`/raidconfig canal`** (choisis le salon du raid).",
                ephemeral=True,
            )
            return
        wk = _week_key(datetime.now(core.TIMEZONE))
        await self._start_boss_raid(interaction.guild, target, wk)
        await interaction.followup.send(f"✅ Raid lancé dans {target.mention}.", ephemeral=True)

    @app_commands.command(name="raidalerttest", description="Envoie un message type « raid dans 1 h » (test admin).")
    @app_commands.default_permissions(administrator=True)
    async def raid_alert_test(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        target = _raid_target_channel(interaction.guild)
        if target is None:
            await interaction.response.send_message(
                "❌ Aucun salon de raid configuré. Utilise d’abord **`/raidconfig canal`**.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await target.send(
                "@here 🧪 **TEST** — dans 1 h ce serait l’alerte avant le **Boss Raid**.",
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Je ne peux pas envoyer de message dans {target.mention}. Vérifie les permissions du bot.",
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : `{e}`", ephemeral=True)
            return
        await interaction.followup.send(f"✅ Message de test envoyé dans {target.mention}.", ephemeral=True)

    # ---------- Chain quiz ----------

    @commands.hybrid_command(name="chainquiz", description="Enchaîne des quiz : difficulté qui monte à chaque bonne réponse.")
    async def chainquiz(self, ctx: commands.Context) -> None:
        if not await _require_slash(ctx, "chainquiz"):
            return
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        qz = self.bot.get_cog("Quiz")
        if not qz:
            await ctx.send("❌ Module quiz indisponible.")
            return

        streak = 0
        total_xp = 0
        await ctx.send(
            "⛓️ **Chain quiz** — une bonne réponse enchaîne avec une difficulté supérieure. "
            "Erreur ou `jsp` = fin. Tape le titre de l’anime (FR/EN/JP)."
        )

        while True:
            diff = SORT_CHAIN[min(streak, len(SORT_CHAIN) - 1)]
            sort_key = SORT_TO_ANILIST[diff]
            anime = await qz._fetch_random_anilist_media(sort_key)  # type: ignore[attr-defined]
            if not anime:
                await ctx.send(core.anilist_error_user_message())
                break
            titles = qz._titles_set(anime)  # type: ignore[attr-defined]
            embed = discord.Embed(
                title=f"⛓️ Chain · Manche {streak + 1} ({diff})",
                description=f"**{20 + streak * 5}s** — quel est cet anime ?",
                color=discord.Color.gold(),
            )
            img = (anime.get("coverImage") or {}).get("extraLarge") or (anime.get("coverImage") or {}).get("large")
            if img:
                embed.set_image(url=img)
            await ctx.send(embed=embed)
            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=float(20 + streak * 5),
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                )
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Fin de chaîne à **{streak}** bonne(s) réponse(s).")
                break
            guess = (msg.content or "").strip()
            if guess.lower() in {"jsp", "pass", "skip"}:
                await ctx.send(f"⏭️ Arrêt — chaîne : **{streak}** · XP gagné : **{total_xp}**.")
                break
            if qz.title_matcher.find_matches(guess, titles):  # type: ignore[attr-defined]
                streak += 1
                xp = 5 + min(streak, 8) * 2
                total_xp += xp
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp, announce=False)
                core.add_mini_score(ctx.author.id, "chainquiz", 1)
                self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_win")
                self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_solo_ok")
                await ctx.send(f"✅ +**{xp}** XP · Chaîne **{streak}** — prochaine manche !")
            else:
                rom = (anime.get("title") or {}).get("romaji") or "?"
                await ctx.send(f"❌ C’était **{rom}**. Chaîne terminée : **{streak}** · XP total : **{total_xp}**.")
                break

    # ---------- Guess who (flou) ----------

    @commands.hybrid_command(
        name="guesswho",
        description="Devine le personnage sur une image floutée — difficulté = flou + récompense XP.",
    )
    @app_commands.describe(
        difficulte="Facile = un peu plus net (+18 XP). Normal (+28). Difficile = très flou (+42).",
    )
    @app_commands.choices(
        difficulte=[
            app_commands.Choice(name="Facile (+18 XP)", value="easy"),
            app_commands.Choice(name="Normal (+28 XP)", value="medium"),
            app_commands.Choice(name="Difficile (+42 XP)", value="hard"),
        ]
    )
    async def guesswho(self, ctx: commands.Context, difficulte: str = "medium") -> None:
        if not await _require_slash(ctx, "guesswho"):
            return
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        div, blur_r, timeout_sec, xp_win = GUESSWHO_MODES.get(difficulte, GUESSWHO_MODES["medium"])
        diff_label = {"easy": "Facile", "medium": "Normal", "hard": "Difficile"}.get(difficulte, "Normal")

        page = random.randint(1, 100)
        query = """
        query ($page: Int) {
          Page(page: $page, perPage: 1) {
            characters(sort: FAVOURITES_DESC) {
              name { full }
              image { large }
              media(type: ANIME) { nodes { title { romaji } } }
            }
          }
        }
        """
        data = core.query_anilist(query, {"page": page})
        if not data or "data" not in data:
            await ctx.send(core.anilist_error_user_message())
            return
        chars = data["data"]["Page"]["characters"]
        if not chars:
            await ctx.send("❌ Pas de personnage.")
            return
        char = chars[0]
        name = char["name"]["full"]
        url = (char.get("image") or {}).get("large")
        nodes = (char.get("media") or {}).get("nodes") or []
        hint = nodes[0]["title"]["romaji"] if nodes else "—"

        buf = io.BytesIO()
        if url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        raw = await resp.read()
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                d = max(3, int(div))
                im = im.resize((max(32, im.width // d), max(32, im.height // d)), Image.Resampling.LANCZOS)
                im = im.resize((im.width * d, im.height * d), Image.Resampling.NEAREST)
                im = im.filter(ImageFilter.GaussianBlur(radius=float(blur_r)))
                im.save(buf, format="PNG")
                buf.seek(0)
            except Exception as e:
                LOG.warning("guesswho blur: %s", e)
                buf = None
        else:
            buf = None

        embed = discord.Embed(
            title="🕵️ Qui est-ce ?",
            description=(
                f"**{diff_label}** — en cas de victoire : **+{xp_win} XP**.\n"
                f"Tape le **nom du personnage** ({int(timeout_sec)} s). Indice anime : _{hint}_"
            ),
            color=discord.Color.purple(),
        )
        if buf:
            embed.set_image(url="attachment://guesswho.png")
            file = discord.File(buf, filename="guesswho.png")
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.send(embed=embed)

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=timeout_sec,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
            )
        except asyncio.TimeoutError:
            await ctx.send(
                f"⏰ Temps écoulé — c’était **{name}** "
                f"_(difficulté **{diff_label}**, récompense prévue **+{xp_win} XP**)_."
            )
            return

        g = (msg.content or "").strip()
        qz = self.bot.get_cog("Quiz")
        ok = False
        if qz:
            ok = bool(qz.title_matcher.find_matches(g, {name}))  # type: ignore[attr-defined]
        if not ok:
            ok = normalize(g) == normalize(name)
        if ok:
            await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp_win, announce=False)
            core.add_mini_score(ctx.author.id, "guesswho", 1)
            await ctx.send(
                f"✅ Bravo ! C’était **{name}** — tu gagnes **+{xp_win} XP** "
                f"_(**{diff_label}**)_."
            )
        else:
            await ctx.send(
                f"❌ Ce n’était pas ça — la réponse était **{name}** "
                f"_(**{diff_label}** aurait rapporté **+{xp_win} XP**)_."
            )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityGames(bot))
